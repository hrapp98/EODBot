from flask import Flask, request, jsonify, render_template, redirect, url_for
from markupsafe import Markup
from datetime import datetime, timedelta
import hmac
import hashlib
import logging
import json
import os
from config import Config
from models import EODReport, SubmissionTracker, EODTracker
from slack_bot import SlackBot
from firebase_client import FirebaseClient
from google.cloud import firestore
from zoneinfo import ZoneInfo
from sheets_client import SheetsClient
from scheduler import setup_scheduler
from flask_compress import Compress
from functools import lru_cache
import time
from flask_assets import Environment, Bundle

# Set up logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Adjust specific loggers
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('openai').setLevel(logging.WARNING)
logging.getLogger('slack_sdk.web.base_client').setLevel(logging.WARNING)
logging.getLogger('googleapiclient.discovery').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Load environment variables
if os.path.exists('.env'):
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("Loaded .env file")

# For Replit secrets
if os.environ.get('REPL_ID'):
    try:
        secrets_path = os.path.join(os.environ.get('REPL_HOME', ''), '.config', 'secrets.json')
        if os.path.exists(secrets_path):
            with open(secrets_path) as f:
                secrets = json.load(f)
                for key, value in secrets.items():
                    os.environ[key] = value
            logger.info("Loaded Replit secrets successfully")
        else:
            logger.warning(f"Secrets file not found at {secrets_path}")
    except Exception as e:
        logger.error(f"Error loading Replit secrets: {str(e)}")

# Verify OpenAI key is loaded
logger.info(f"OpenAI API key loaded: {bool(os.environ.get('OPENAI_API_KEY'))}")

def create_app():
    """Initialize and configure Flask application"""
    try:
        logger.info("Creating Flask application...")
        app = Flask(__name__)
        app.secret_key = Config.FLASK_SECRET_KEY
        
        # Add compression
        Compress(app)
        
        # Set up logging middleware
        @app.before_request
        def before_request_logging():
            logger.debug(f"Incoming {request.method} request to {request.path}")
            if request.is_json:
                logger.debug(f"Request payload: {request.json}")

        @app.after_request
        def after_request_logging(response):
            logger.debug(f"Request completed with status {response.status_code}")
            return response
            
        # Set up asset bundling and minification
        assets = Environment(app)
        
        # CSS bundle
        css = Bundle(
            'css/style.css',
            filters='cssmin',
            output='gen/packed.css'
        )
        
        # JS bundle
        js = Bundle(
            'js/main.js',
            filters='jsmin',
            output='gen/packed.js'
        )
        
        assets.register('css_all', css)
        assets.register('js_all', js)
        
        logger.info("Application creation successful")
        return app
    except Exception as e:
        logger.error(f"Failed to create application: {str(e)}")
        raise

app = create_app()

# Add custom template filters
@app.template_filter('nl2br')
def nl2br_filter(text):
    """Convert newlines to HTML line breaks"""
    if not text:
        return ""
    return Markup(text.replace('\n', '<br>'))

# Initialize global clients
firebase_client = FirebaseClient() if Config.firebase_config_valid() else None

# Fix SlackBot initialization
try:
    slack_bot = None
    if Config.SLACK_BOT_TOKEN:
        slack_bot = SlackBot()
        slack_bot.client.token = Config.SLACK_BOT_TOKEN
        logger.info("SlackBot initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize SlackBot: {str(e)}")
    slack_bot = None

sheets_client = SheetsClient() if Config.GOOGLE_SERVICE_ACCOUNT else None

# Cache for team data
_team_cache = None
_team_cache_time = 0
_team_cache_ttl = 300  # 5 minutes

@app.route('/')
def index():
    """Redirect to dashboard"""
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    """Render dashboard with minimal initial data and async loading"""
    try:
        # Get minimal data needed for initial render
        now = datetime.now(ZoneInfo("America/New_York"))
        today = now.date()
        
        # Add a loading indicator for team members
        return render_template(
            'dashboard.html',
            total_users="Loading...",
            submitted_count="Loading...",
            submission_rate="Loading...",
            reports=[],
            users={},  # Empty users dict - will be loaded via AJAX
            initial_load=True,
            trend_data=[]  # Empty trend data - will be loaded via AJAX
        )
    except Exception as e:
        logger.error(f"Error loading dashboard: {str(e)}")
        return "Error loading dashboard. Please check server logs.", 500

@app.route('/api/dashboard-data')
def dashboard_data():
    """API endpoint to get dashboard data asynchronously"""
    try:
        # Get today's date in NY timezone
        now = datetime.now(ZoneInfo("America/New_York"))
        today = now.date()
        
        # Get all active users
        users_query = firebase_client.db.collection('users').where('status', '==', 'active').stream()
        total_users = 0
        for _ in users_query:
            total_users += 1
            
        # Get today's submissions
        date_str = today.strftime('%Y-%m-%d')
        submitted_users = set()
        
        docs = firebase_client.db.collection('eod_reports').where('date', '==', date_str).stream()
        for doc in docs:
            data = doc.to_dict()
            user_id = data.get('user_id')
            if user_id:
                submitted_users.add(user_id)
        
        # Calculate stats
        submitted_count = len(submitted_users)
        submission_rate = round(submitted_count / total_users * 100 if total_users > 0 else 0, 1)
        
        # Get trend data for the last 7 days
        trend_data = []
        current = today - timedelta(days=6)  # Last 7 days including today
        
        while current <= today:
            date_str = current.strftime('%Y-%m-%d')
            day_submissions = set()
            
            docs = firebase_client.db.collection('eod_reports').where('date', '==', date_str).stream()
            for doc in docs:
                data = doc.to_dict()
                user_id = data.get('user_id')
                if user_id:
                    day_submissions.add(user_id)
            
            rate = len(day_submissions) / total_users * 100 if total_users > 0 else 0
            
            trend_data.append({
                'date': current.strftime('%m/%d'),
                'rate': round(rate, 1)
            })
            current += timedelta(days=1)
        
        return jsonify({
            'total_users': total_users,
            'submitted_count': submitted_count,
            'submission_rate': submission_rate,
            'trend_data': trend_data
        })
        
    except Exception as e:
        logger.error(f"Error getting dashboard data: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/slack/events', methods=['POST'])
def slack_events():
    """Handle Slack events"""
    try:
        # Verify request signature
        timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
        signature = request.headers.get('X-Slack-Signature', '')
        
        if not timestamp or not signature:
            logger.warning("Missing Slack verification headers")
            return jsonify({'error': 'missing_headers'}), 400
            
        if abs(datetime.now().timestamp() - float(timestamp)) > 60 * 5:
            logger.warning("Request timestamp too old")
            return jsonify({'error': 'invalid_timestamp'}), 403
            
        sig_basestring = f"v0:{timestamp}:{request.get_data(as_text=True)}"
        my_signature = 'v0=' + hmac.new(
            Config.SLACK_SIGNING_SECRET.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(my_signature, signature):
            logger.warning("Invalid request signature")
            return jsonify({'error': 'invalid_signature'}), 403

        # Parse request data
        if not request.is_json:
            logger.warning("Request is not JSON")
            return jsonify({'error': 'invalid_content_type'}), 415
            
        data = request.json
        
        # Handle URL verification
        if data.get('type') == 'url_verification':
            return jsonify({'challenge': data['challenge']})
        
        # Handle events
        if data.get('type') == 'event_callback':
            event = data.get('event', {})
            event_type = event.get('type')
            
            if event_type == 'message' and 'bot_id' not in event:
                handle_message(event)
            elif event_type == 'app_mention':
                handle_app_mention(event)
                
        return jsonify({'status': 'ok'})
        
    except Exception as e:
        logger.error(f"Error handling Slack event: {str(e)}")
        return jsonify({'error': 'internal_error'}), 500

def handle_message(event):
    """Process incoming messages"""
    try:
        text = event.get('text', '').lower()
        user_id = event.get('user')
        channel_type = event.get('channel_type', '')
        channel_id = event.get('channel')  # Get the channel/DM ID
        
        logger.debug(f"Processing message from user {user_id}: {text}")
        
        # Skip if this is a bot message
        if event.get('bot_id') or event.get('subtype') == 'bot_message':
            return
            
        # DON'T handle /eod command here - it's handled by slack_commands()
        # Only handle direct EOD submissions in the format "submit eod: ..."
        if text.startswith('submit eod:'):
            handle_eod_submission(event)
        # Silently ignore other messages (including /eod commands)
        return
            
    except Exception as e:
        logger.error(f"Error handling message: {str(e)}")
        # Only send error message if we were trying to handle an EOD submission
        if text and text.startswith('submit eod:'):
            slack_bot.send_error_message(user_id)

def handle_app_mention(event):
    """Handle when the bot is mentioned"""
    try:
        text = event.get('text', '').lower().replace(f'<@{event.get("bot_id", "")}>', '').strip()
        user_id = event.get('user')
        channel_id = event.get('channel')  # Get the channel ID
        
        logger.debug(f"Processing mention from user {user_id}: {text}")
        
        if 'eod report' in text:
            # Pass the channel ID in private_metadata
            trigger_id = event.get('trigger_id')
            if trigger_id:
                private_metadata = json.dumps({'channel_id': channel_id})
                slack_bot.send_eod_prompt(trigger_id, private_metadata)
        elif text.startswith('submit eod:'):
            handle_eod_submission(event)
        elif 'status' in text:
            slack_bot.send_status_update(user_id)
        elif 'help' in text or text == '':
            slack_bot.send_help_message(user_id)
            
    except Exception as e:
        logger.error(f"Error handling mention: {str(e)}")
        slack_bot.send_error_message(user_id)

def handle_eod_submission(event):
    """Process EOD report submission"""
    try:
        user_id = event.get('user')
        text = event.get('text').replace('submit eod:', '', 1).strip()
        
        # Create and save EOD report
        report = EODReport.create_from_text(user_id, text)
        
        # Save report to Firebase
        if firebase_client:
            try:
                firebase_client.save_eod_report(report.user_id, report.to_dict())
            except Exception as e:
                logger.error(f"Failed to save report to Firebase: {str(e)}")
                raise
        
        # Post to Slack channel
        slack_bot.post_report_to_channel(report.to_dict())
        slack_bot.send_message(user_id, "Your EOD report has been submitted successfully!")
            
    except Exception as e:
        logger.error(f"Error processing submission: {str(e)}")
        slack_bot.send_error_message(event.get('user'))

@app.route('/slack/commands', methods=['POST'])
def slack_commands():
    """Handle Slack slash commands"""
    try:
        logger.debug("Incoming POST request to /slack/commands")
        command = request.form.get('command')
        user_id = request.form.get('user_id')
        channel_id = request.form.get('channel_id')
        trigger_id = request.form.get('trigger_id')
        
        if command == '/eod':
            # Check for existing report
            if firebase_client:
                try:
                    today = datetime.now(ZoneInfo("America/New_York")).date()
                    existing_report = firebase_client.get_user_report_for_date(user_id, today)
                    
                    if existing_report:
                        # Send message with interactive buttons
                        slack_bot.send_already_submitted_message(channel_id, user_id, today)
                        return ('', 200)  # Return empty 200 response with no content
                    else:
                        # No existing report, open the modal
                        slack_bot.send_eod_prompt(trigger_id)
                        return jsonify({
                            'response_type': 'ephemeral',
                            'text': 'Opening EOD report form...'
                        })
                except Exception as e:
                    logger.error(f"Error checking existing report: {str(e)}")
                    return jsonify({
                        'response_type': 'ephemeral',
                        'text': 'Sorry, there was an error checking your report status.'
                    }), 500
            else:
                logger.error("Firebase client not initialized")
                return jsonify({
                    'response_type': 'ephemeral',
                    'text': 'Sorry, the EOD report system is not properly configured.'
                }), 500
            
    except Exception as e:
        logger.error(f"Error handling slash command: {str(e)}")
        return jsonify({
            'response_type': 'ephemeral',
            'text': 'Sorry, something went wrong processing your command.'
        }), 500

@app.route('/slack/interactive-endpoint', methods=['POST'])
def slack_interactivity():
    """Handle Slack interactive components"""
    try:
        if request.form.get('payload'):
            payload = json.loads(request.form['payload'])
            logger.debug(f"Full payload: {payload}")
            
            if payload['type'] == 'view_submission':
                logger.info("Received view submission")
                
                # Extract values from the submission
                values = payload['view']['state']['values']
                report_data = {
                    'short_term_projects': values['short_term_block']['short_term_input']['value'],
                    'long_term_projects': values['long_term_block']['long_term_input']['value'],
                    'blockers': values['blockers_block']['blockers_input']['value'],
                    'next_day_goals': values['goals_block']['goals_input']['value'],
                    'tools_used': values['tools_block']['tools_input']['value'],
                    'help_needed': values['help_block']['help_input']['value'],
                    'client_feedback': values['client_feedback_block']['client_feedback_input']['value']
                }
                
                user_id = payload['user']['id']
                report_data['user_id'] = user_id  # Add user_id to report_data
                
                # Check if this is an edit
                try:
                    metadata = json.loads(payload['view'].get('private_metadata', '{}'))
                    is_edit = metadata.get('is_edit', False)
                    report_id = metadata.get('report_id')
                except json.JSONDecodeError:
                    logger.warning("Invalid private_metadata JSON, treating as new submission")
                    is_edit = False
                    report_id = None

                # Close the modal immediately
                response = {"response_action": "clear"}
                
                # Handle background tasks directly without closure
                def process_submission():
                    try:
                        # Save to Firebase
                        nonlocal report_id  # Access the outer scope variable
                        saved_report_id = None
                        
                        if is_edit and report_id:
                            firebase_client.update_eod_report(report_id, report_data)
                            saved_report_id = report_id
                        else:
                            saved_report_id = firebase_client.save_eod_report(user_id, report_data)
                            report_id = saved_report_id  # Update the outer scope variable

                        # Update Google Sheets
                        if sheets_client and sheets_client.service:
                            try:
                                sheets_client.update_submissions(report_data)
                                sheets_client.update_tracker()
                            except Exception as e:
                                logger.error(f"Error updating sheets: {str(e)}")

                        # Post to channel
                        slack_bot.post_report_to_channel(report_data)
                        
                        # Send confirmation message to user
                        action_type = "updated" if is_edit else "submitted"
                        slack_bot.send_message(user_id, f"Your EOD report has been {action_type} successfully!")
                        
                        # Generate weekly summary if in debug mode
                        try:
                            if Config.DEBUG:
                                generate_weekly_summary(app)
                                logger.info(f"Generated weekly summary after {action_type} (debug mode)")
                        except Exception as e:
                            logger.error(f"Error generating debug weekly summary: {str(e)}")
                            
                    except Exception as e:
                        logger.error(f"Error in background tasks: {str(e)}")
                        slack_bot.send_message(user_id, "There was an error processing your submission. Please try again or contact support.")

                # Start background tasks in a new thread
                from threading import Thread
                Thread(target=process_submission).start()
                
                return jsonify(response)

            elif payload['type'] == 'block_actions':
                # Handle button clicks
                action_id = payload['actions'][0]['action_id']
                if action_id in ['view_report', 'edit_report']:
                    user_id = payload['user']['id']
                    today = datetime.now(ZoneInfo("America/New_York")).date()
                    report = firebase_client.get_user_report_for_date(user_id, today)
                    
                    if not report:
                        # Handle case where report doesn't exist
                        return jsonify({
                            "response_type": "ephemeral",
                            "text": "Could not find today's report. It may have been deleted."
                        })
                    
                    if action_id == 'edit_report':
                        metadata = {
                            'is_edit': True,
                            'report_id': report['id']
                        }
                        slack_bot.send_eod_prompt(
                            trigger_id=payload['trigger_id'],
                            private_metadata=json.dumps(metadata),
                            existing_data=report
                        )
                    else:  # view_report
                        # Show report in a message
                        channel_id = payload['container']['channel_id']
                        formatted_report = slack_bot._format_report_for_channel(report)
                        slack_bot.client.chat_postEphemeral(
                            channel=channel_id,
                            user=user_id,
                            text=formatted_report,
                            parse='mrkdwn'
                        )
                        
                    return jsonify({"message": "Processing action"})

    except Exception as e:
        logger.error(f"Error in slack_interactivity: {str(e)}")
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "Success"}), 200

@app.route('/dashboard/report/<report_id>')
def view_report(report_id):
    """View detailed EOD report"""
    try:
        if not firebase_client:
            return "Firebase client not initialized. Please check configuration.", 500
            
        # Get report from Firebase
        doc_ref = firebase_client.db.collection('eod_reports').document(report_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return "Report not found", 404
            
        report_data = doc.to_dict()
        user_id = report_data.get('user_id')
        
        # Get user info
        user_info = None
        try:
            user_info = slack_bot.client.users_info(user=user_id)
            user_data = {
                'name': user_info['user']['real_name'],
                'image': user_info['user']['profile'].get('image_192', ''),
                'email': user_info['user']['profile'].get('email', ''),
                'title': user_info['user']['profile'].get('title', '')
            }
        except Exception as e:
            logger.error(f"Error getting user info: {str(e)}")
            user_data = {
                'name': report_data.get('user_name', 'Unknown User'),
                'image': '',
                'email': report_data.get('user_email', ''),
                'title': ''
            }
            
        # Format timestamp
        timestamp = report_data.get('timestamp')
        if timestamp:
            if isinstance(timestamp, datetime):
                formatted_date = timestamp.astimezone(ZoneInfo("America/New_York")).strftime('%Y-%m-%d %H:%M:%S')
            else:
                formatted_date = timestamp
        else:
            formatted_date = 'Unknown'
            
        return render_template(
            'report_detail.html',
            report=report_data,
            report_id=report_id,
            user=user_data,
            formatted_date=formatted_date
        )
    except Exception as e:
        logger.error(f"Error viewing report: {str(e)}")
        return "Error viewing report. Please check server logs.", 500

@app.route('/api/users', methods=['POST'])
def add_user():
    """Add a new user to the system"""
    try:
        data = request.json
        
        # Validate required fields
        if not data or 'slack_id' not in data:
            return jsonify({'error': 'Missing required field: slack_id'}), 400
            
        slack_id = data.get('slack_id')
        
        # Get user info from Slack to verify the ID
        try:
            user_info = slack_bot.client.users_info(user=slack_id)
            if not user_info.get('ok', False):
                return jsonify({'error': 'Invalid Slack user ID'}), 400
                
            user_name = user_info['user']['real_name']
            user_email = user_info['user'].get('profile', {}).get('email', '')
        except Exception as e:
            logger.error(f"Error verifying Slack user: {str(e)}")
            return jsonify({'error': 'Could not verify Slack user ID'}), 400
        
        # Add user to Firebase
        user_data = {
            'slack_id': slack_id,
            'name': user_name,
            'email': user_email,
            'status': 'active',
            'created_at': datetime.now(ZoneInfo("UTC"))
        }
        
        # Add custom fields if provided
        for field in ['role', 'team', 'timezone']:
            if field in data:
                user_data[field] = data[field]
        
        # Save to Firebase
        user_id = firebase_client.add_user(user_data)
        
        if user_id:
            return jsonify({
                'success': True,
                'message': f'User {user_name} added successfully',
                'user_id': user_id
            })
        else:
            return jsonify({'error': 'Failed to add user'}), 500
            
    except Exception as e:
        logger.error(f"Error adding user: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<slack_id>/status', methods=['PUT'])
def update_user_status(slack_id):
    """Update a user's active status"""
    try:
        data = request.json
        
        if not data or 'status' not in data:
            return jsonify({'error': 'Missing required field: status'}), 400
            
        status = data.get('status')
        if status not in ['active', 'inactive']:
            return jsonify({'error': 'Status must be either "active" or "inactive"'}), 400
        
        # Update user status in Firebase
        success = firebase_client.update_user_status(slack_id, status)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'User status updated to {status}'
            })
        else:
            return jsonify({'error': 'Failed to update user status'}), 500
            
    except Exception as e:
        logger.error(f"Error updating user status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users', methods=['GET'])
def get_users():
    """Get all users"""
    try:
        users = firebase_client.get_all_users()
        return jsonify({'users': users})
    except Exception as e:
        logger.error(f"Error getting users: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/user/<user_id>')
def user_profile(user_id):
    """View user profile with submission history"""
    try:
        # Get Slack bot and Firebase client
        slack_bot = SlackBot()
        slack_bot.client.token = Config.SLACK_BOT_TOKEN
        firebase_client = FirebaseClient()
        
        # Get user profile data
        user_data = slack_bot.get_user_profile_data(user_id)
        if not user_data:
            return "User not found", 404
            
        # Get submission calendar
        submission_calendar = user_data.get('submission_calendar', {})
        
        # Get current year and today's date
        now = datetime.now(ZoneInfo("America/New_York"))
        current_year = now.year
        today_date = now.date().isoformat()
        
        # Find the first submission date
        first_submission_date = None
        if submission_calendar:
            # Sort dates and get the earliest one
            sorted_dates = sorted(submission_calendar.keys())
            if sorted_dates:
                first_submission_date = sorted_dates[0]
        
        # If no submissions yet, set first_submission_date to today to avoid showing any missed days
        if not first_submission_date:
            first_submission_date = today_date
        
        # Calculate missed submissions
        # Get all weekdays in the current year
        start_date = datetime(current_year, 1, 1, tzinfo=ZoneInfo("America/New_York"))
        end_date = now if now.year == current_year else datetime(current_year, 12, 31, tzinfo=ZoneInfo("America/New_York"))
        
        # Generate all weekdays (Monday-Friday) in the date range
        all_weekdays = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:  # Monday-Friday
                all_weekdays.append(current.date().isoformat())
            current += timedelta(days=1)
        
        # Find missed submissions (weekdays without submissions)
        missed_dates = []
        for day in all_weekdays:
            if day not in submission_calendar and day <= today_date and day >= first_submission_date:
                missed_dates.append(day)
        
        # Helper function to check if a date is valid
        def is_valid_date(year, month, day):
            try:
                datetime(year, month, day)
                return True
            except ValueError:
                return False
        
        # Get recent reports
        reports = []
        
        # Get page parameter for pagination
        page = request.args.get('page', 1, type=int)
        per_page = 5  # Number of reports per page
        
        # Query for user's reports with pagination
        reports_query = firebase_client.db.collection('eod_reports')\
            .where('user_id', '==', user_id)\
            .order_by('timestamp', direction=firestore.Query.DESCENDING)\
            .limit(per_page + 1)\
            .offset((page - 1) * per_page)
        
        reports_docs = reports_query.stream()
        
        # Process reports
        for doc in reports_docs:
            if len(reports) >= per_page:
                # We have one more document than we need, which means there's a next page
                has_next = True
                break
                
            data = doc.to_dict()
            timestamp = data.get('timestamp')
            
            if timestamp:
                # Convert to NY timezone
                timestamp_ny = timestamp.astimezone(ZoneInfo("America/New_York"))
                date_str = timestamp_ny.strftime('%Y-%m-%d')
                time_str = timestamp_ny.strftime('%I:%M %p')
            else:
                date_str = 'Unknown'
                time_str = 'Unknown'
            
            reports.append({
                'id': doc.id,
                'date': date_str,
                'time': time_str,
                'short_term_projects': data.get('short_term_projects', ''),
                'long_term_projects': data.get('long_term_projects', ''),
                'blockers': data.get('blockers', ''),
                'next_day_goals': data.get('next_day_goals', ''),
                'tools_used': data.get('tools_used', ''),
                'help_needed': data.get('help_needed', ''),
                'client_feedback': data.get('client_feedback', '')
            })
        
        # Calculate total pages
        # This is an approximation - for exact count we would need to count all documents
        total_pages = page + 1 if len(reports) == per_page else page
        
        # Get weekly summaries
        summaries = []
        
        # Query for user's summaries
        summaries_query = firebase_client.db.collection('weekly_summaries')\
            .where('user_id', '==', user_id)\
            .order_by('end_date', direction=firestore.Query.DESCENDING)\
            .limit(10)  # Limit to 10 most recent summaries
        
        summaries_docs = summaries_query.stream()
        
        # Process summaries
        for doc in summaries_docs:
            data = doc.to_dict()
            start_date = data.get('start_date')
            end_date = data.get('end_date')
            
            if start_date and end_date:
                # Convert to NY timezone if they are timestamps
                if isinstance(start_date, datetime):
                    start_date = start_date.astimezone(ZoneInfo("America/New_York")).strftime('%Y-%m-%d')
                if isinstance(end_date, datetime):
                    end_date = end_date.astimezone(ZoneInfo("America/New_York")).strftime('%Y-%m-%d')
            else:
                start_date = 'Unknown'
                end_date = 'Unknown'
            
            summaries.append({
                'id': doc.id,
                'start_date': start_date,
                'end_date': end_date,
                'summary': data.get('summary', '')
            })
        
        # Calculate missed submissions count - only count days after first submission
        missed_submissions = [date for date in missed_dates if date >= first_submission_date and date <= today_date]
        
        return render_template(
            'user_profile.html',
            user=user_data,
            reports=reports,
            submission_calendar=submission_calendar,
            missed_dates=missed_dates,
            missed_submissions=missed_submissions,  # This is now correctly filtered
            is_valid_date=is_valid_date,
            current_year=current_year,
            today_date=today_date,
            first_submission_date=first_submission_date,
            page=page,
            total_pages=total_pages,
            summaries=summaries
        )
        
    except Exception as e:
        logger.error(f"Error loading user profile: {str(e)}")
        return "Error loading user profile. Please check server logs.", 500

@app.route('/dashboard/user/<user_id>')
def redirect_user_profile(user_id):
    """Redirect from old URL pattern to new one"""
    return redirect(url_for('user_profile', user_id=user_id))

def sync_users_from_slack():
    """Sync users from Slack to Firebase with more data"""
    try:
        # Get all users from Slack
        response = slack_bot.client.users_list()
        slack_users = response["members"]
        logger.info(f"Retrieved {len(slack_users)} users from Slack")
        
        # Process each Slack user
        for slack_user in slack_users:
            # Skip bots and deleted users
            if slack_user.get('is_bot', False) or slack_user.get('deleted', False):
                continue
                
            # Skip special users like Slackbot
            if slack_user['id'] == 'USLACKBOT':
                continue
                
            # Prepare user data
            user_data = {
                'slack_id': slack_user['id'],
                'name': slack_user['real_name'],
                'display_name': slack_user['profile'].get('display_name', ''),
                'email': slack_user['profile'].get('email', ''),
                'status': 'active',
                'created_at': datetime.now(ZoneInfo("UTC")),
                'updated_at': datetime.now(ZoneInfo("UTC")),
                'auto_added': True,
                'title': slack_user['profile'].get('title', ''),
                'image': slack_user['profile'].get('image_512', ''),
                'timezone': slack_user.get('tz', 'Unknown')
            }
            
            # Add user to Firebase
            firebase_client.add_user(user_data)
            
    except Exception as e:
        logger.error(f"Error syncing users from Slack: {str(e)}")

# Modify the initialize_internal_users function to call sync_users_from_slack
def initialize_internal_users():
    """Initialize internal team users and sync all Slack users"""
    internal_users = [
        {
            'slack_id': 'U083K838X8V',
            'name': 'Harlan Rappaport',
            'email': 'harlan@hireoverseas.com',
            'status': 'active'
        },
        {
            'slack_id': 'U0890AG4ZEU',
            'name': 'Internal User 2',
            'status': 'active'
        },
        {
            'slack_id': 'U0837HZE98X',
            'name': 'Internal User 3',
            'status': 'active'
        },
        {
            'slack_id': 'U08CSFHTJ2X',
            'name': 'Internal User 4',
            'status': 'active'
        }
    ]
    
    # First add internal users
    for user in internal_users:
        try:
            if 'created_at' not in user:
                user['created_at'] = datetime.now(ZoneInfo("UTC"))
            user['auto_added'] = True
            firebase_client.add_user(user)
        except Exception as e:
            logger.error(f"Error initializing user {user['name']}: {str(e)}")
    
    # Then sync all users from Slack
    sync_users_from_slack()

@app.route('/stats/<date_range>')
def get_stats(date_range):
    """Get submission statistics for the given date range"""
    try:
        # Get today's date in NY timezone
        now = datetime.now(ZoneInfo("America/New_York"))
        today = now.date()
        
        # Calculate date range
        if date_range == 'today':
            start_date = today
            end_date = today
            is_single_day = True
        elif date_range == 'yesterday':
            start_date = today - timedelta(days=1)
            end_date = start_date
            is_single_day = True
        else:
            try:
                days = int(date_range)
                start_date = today - timedelta(days=days-1)
                end_date = today
                is_single_day = False
            except ValueError:
                return jsonify({'error': 'Invalid date range'}), 400
        
        # Get all users
        users_query = firebase_client.db.collection('users').where('status', '==', 'active').stream()
        total_users = 0
        for _ in users_query:
            total_users += 1
        
        # Get submissions in date range
        current = start_date
        submitted_users = set()
        submission_counts = []  # Track submissions per day
        working_days = 0  # Count only working days
        
        while current <= end_date:
            # Skip weekends
            if current.weekday() < 5:  # 0-4 are Monday-Friday
                working_days += 1
                
                # Get submissions for this day
                date_str = current.strftime('%Y-%m-%d')
                day_submissions = set()
                
                docs = firebase_client.db.collection('eod_reports').where('date', '==', date_str).stream()
                for doc in docs:
                    data = doc.to_dict()
                    user_id = data.get('user_id')
                    if user_id:
                        day_submissions.add(user_id)
                        submitted_users.add(user_id)
                
                submission_counts.append(len(day_submissions))
            
            current += timedelta(days=1)
        
        # Calculate trend data
        trend_data = []
        current = start_date
        while current <= end_date:
            date_str = current.strftime('%Y-%m-%d')
            
            # Get submissions for this day
            day_submissions = set()
            docs = firebase_client.db.collection('eod_reports').where('date', '==', date_str).stream()
            for doc in docs:
                data = doc.to_dict()
                user_id = data.get('user_id')
                if user_id:
                    day_submissions.add(user_id)
            
            # Calculate rate for this day
            rate = len(day_submissions) / total_users * 100 if total_users > 0 else 0
            
            trend_data.append({
                'date': current.strftime('%m/%d'),
                'rate': round(rate, 1)
            })
            current += timedelta(days=1)
        
        # Calculate average daily submissions for multi-day ranges
        if is_single_day:
            submitted_count = len(submitted_users)
            submission_rate = round(submitted_count / total_users * 100 if total_users > 0 else 0, 1)
            label_prefix = ""
        else:
            # Calculate average daily submissions
            avg_daily_submissions = sum(submission_counts) / working_days if working_days > 0 else 0
            avg_daily_rate = sum(submission_counts) / (working_days * total_users) * 100 if working_days > 0 and total_users > 0 else 0
            submitted_count = round(avg_daily_submissions, 1)
            submission_rate = round(avg_daily_rate, 1)
            label_prefix = "Avg. Daily "
        
        return jsonify({
            'total_users': total_users,
            'submitted_count': submitted_count,
            'submission_rate': submission_rate,
            'submitted_users': list(submitted_users),
            'trend_data': trend_data,
            'is_single_day': is_single_day,
            'label_prefix': label_prefix
        })
        
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/stats/specific/<date_str>')
def get_specific_date_stats(date_str):
    """Get submission statistics for a specific date"""
    try:
        # Parse the date string (format: YYYY-MM-DD)
        try:
            specific_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        # Get all users
        users_query = firebase_client.db.collection('users').where('status', '==', 'active').stream()
        total_users = 0
        for _ in users_query:
            total_users += 1
        
        # Get submissions for this specific date
        date_str = specific_date.strftime('%Y-%m-%d')
        submitted_users = set()
        
        docs = firebase_client.db.collection('eod_reports').where('date', '==', date_str).stream()
        for doc in docs:
            data = doc.to_dict()
            user_id = data.get('user_id')
            if user_id:
                submitted_users.add(user_id)
        
        # Calculate stats
        submitted_count = len(submitted_users)
        submission_rate = round(submitted_count / total_users * 100 if total_users > 0 else 0, 1)
        
        # Create trend data with just this one date
        trend_data = [{
            'date': specific_date.strftime('%m/%d'),
            'rate': submission_rate
        }]
        
        return jsonify({
            'total_users': total_users,
            'submitted_count': submitted_count,
            'submission_rate': submission_rate,
            'submitted_users': list(submitted_users),
            'trend_data': trend_data,
            'is_single_day': True,
            'label_prefix': ""
        })
        
    except Exception as e:
        logger.error(f"Error getting specific date stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/missed')
@app.route('/missed/<int:days>')
def missed_submissions(days=30):
    """View missed submissions"""
    try:
        # Default to 30 days if not specified
        days = min(max(days, 1), 90)  # Limit between 1 and 90 days
        
        # Return a minimal template that will load data asynchronously
        return render_template(
            'missed_submissions.html',
            days=days,
            missed_submissions={},  # Empty dict - will be loaded via AJAX
            initial_load=True
        )
    except Exception as e:
        logger.error(f"Error loading missed submissions page: {str(e)}")
        return "Error loading missed submissions. Please check server logs.", 500

@app.route('/api/send_reminder', methods=['POST'])
def send_reminder():
    """API endpoint to send a reminder to a user"""
    try:
        data = request.json
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({'success': False, 'error': 'Missing user_id'}), 400
            
        # Send reminder
        slack_bot = SlackBot()
        slack_bot.client.token = Config.SLACK_BOT_TOKEN
        slack_bot.send_reminder(user_id)
        
        # Record that a reminder was sent
        firebase_client = FirebaseClient()
        firebase_client.save_reminder(user_id)
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error sending reminder: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/team')
def team():
    """Render team members page with caching"""
    global _team_cache, _team_cache_time
    
    # Check if cache is valid
    current_time = time.time()
    if _team_cache and current_time - _team_cache_time < _team_cache_ttl:
        return _team_cache
    
    try:
        # Render a loading page that will fetch data via AJAX
        rendered_template = render_template('team.html', users={})
        _team_cache = rendered_template
        _team_cache_time = current_time
        
        return rendered_template
    except Exception as e:
        logger.error(f"Error loading team page: {str(e)}")
        return "Error loading team page. Please check server logs.", 500

@app.route('/api/team-data')
def team_data():
    """API endpoint to get team data for async loading - highly optimized version"""
    try:
        # First check if we have users in Firebase
        users_collection = firebase_client.db.collection('users')
        firebase_users = list(users_collection.stream())
        
        # If we have users in Firebase, use them instead of Slack API
        if firebase_users:
            logger.info(f"Using {len(firebase_users)} users from Firebase cache")
            users_data = {}
            
            # Get today's date in NY timezone
            now = datetime.now(ZoneInfo("America/New_York"))
            today = now.date()
            
            # For reporting purposes, we'll use the last working day
            reporting_day = today
            
            # If it's a weekend, use Friday's date
            if now.weekday() >= 5:  # 5=Saturday, 6=Sunday
                days_to_subtract = now.weekday() - 4  # 4=Friday
                reporting_day = (now - timedelta(days=days_to_subtract)).date()
            
            # Get all submissions for the reporting day
            reporting_day_start = datetime.combine(reporting_day, datetime.min.time()).replace(tzinfo=ZoneInfo("America/New_York"))
            
            # If today is a weekend, include all weekend submissions up to now
            if now.weekday() >= 5:  # Weekend
                reporting_day_end = now.replace(tzinfo=ZoneInfo("America/New_York"))
            else:
                reporting_day_end = datetime.combine(reporting_day, datetime.max.time()).replace(tzinfo=ZoneInfo("America/New_York"))
            
            # Convert to UTC for Firebase query
            reporting_day_start_utc = reporting_day_start.astimezone(ZoneInfo("UTC"))
            reporting_day_end_utc = reporting_day_end.astimezone(ZoneInfo("UTC"))
            
            # Query for reporting day's submissions (including weekend submissions if applicable)
            submitted_on_reporting_day = set()
            reporting_day_query = firebase_client.db.collection('eod_reports').select(['user_id'])
            reporting_day_query = reporting_day_query.where(filter=firestore.FieldFilter('timestamp', '>=', reporting_day_start_utc))
            reporting_day_query = reporting_day_query.where(filter=firestore.FieldFilter('timestamp', '<=', reporting_day_end_utc))
            reporting_day_docs = reporting_day_query.stream()
            
            for doc in reporting_day_docs:
                data = doc.to_dict()
                user_id = data.get('user_id')
                if user_id:
                    submitted_on_reporting_day.add(user_id)
            
            # Process Firebase users
            for doc in firebase_users:
                user_data = doc.to_dict()
                user_id = user_data.get('slack_id')
                
                # Skip if not a valid user
                if not user_id or user_id == 'USLACKBOT':
                    continue
                
                # Skip if user is inactive
                if user_data.get('status') != 'active':
                    continue
                
                # Add user to users_data
                users_data[user_id] = {
                    'id': user_id,  # Make sure this is included
                    'name': user_data.get('name', 'Unknown'),
                    'email': user_data.get('email', ''),
                    'title': user_data.get('title', ''),
                    'image': user_data.get('image', ''),
                    'today_status': 'submitted' if user_id in submitted_on_reporting_day else 'missed'
                }
            
            # Return the data as JSON
            return jsonify(list(users_data.values()))
        else:
            # Fallback to Slack API if no users in Firebase
            logger.info("No users found in Firebase, falling back to Slack API")
            return team_data_fallback()
            
    except Exception as e:
        logger.error(f"Error getting team data: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sync-users', methods=['POST'])
def api_sync_users():
    """API endpoint to sync users from Slack"""
    try:
        sync_users_from_slack()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error syncing users: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/team-members')
def api_team_members():
    """API endpoint to get team members for dashboard"""
    try:
        # Get today's date in NY timezone
        now = datetime.now(ZoneInfo("America/New_York"))
        today = now.date()
        
        # For reporting purposes, we'll use the last working day
        reporting_day = today
        
        # If it's a weekend, use Friday's date
        if now.weekday() >= 5:  # 5=Saturday, 6=Sunday
            days_to_subtract = now.weekday() - 4  # 4=Friday
            reporting_day = (now - timedelta(days=days_to_subtract)).date()
            logger.info(f"Weekend detected, using last Friday: {reporting_day}")
        
        # Get all submissions for the reporting day
        reporting_day_start = datetime.combine(reporting_day, datetime.min.time()).replace(tzinfo=ZoneInfo("America/New_York"))
        
        # If today is a weekend, include all weekend submissions up to now
        if now.weekday() >= 5:  # Weekend
            reporting_day_end = now.replace(tzinfo=ZoneInfo("America/New_York"))
        else:
            reporting_day_end = datetime.combine(reporting_day, datetime.max.time()).replace(tzinfo=ZoneInfo("America/New_York"))
        
        # Convert to UTC for Firebase query
        reporting_day_start_utc = reporting_day_start.astimezone(ZoneInfo("UTC"))
        reporting_day_end_utc = reporting_day_end.astimezone(ZoneInfo("UTC"))
        
        # Query for reporting day's submissions
        submitted_on_reporting_day = set()
        reporting_day_query = firebase_client.db.collection('eod_reports').select(['user_id'])
        reporting_day_query = reporting_day_query.where(filter=firestore.FieldFilter('timestamp', '>=', reporting_day_start_utc))
        reporting_day_query = reporting_day_query.where(filter=firestore.FieldFilter('timestamp', '<=', reporting_day_end_utc))
        reporting_day_docs = reporting_day_query.stream()
        
        for doc in reporting_day_docs:
            data = doc.to_dict()
            user_id = data.get('user_id')
            if user_id:
                submitted_on_reporting_day.add(user_id)
        
        # Get all users who have ever submitted an EOD report
        all_eod_submitters = set()
        eod_docs = firebase_client.db.collection('eod_reports').select(['user_id']).stream()
        
        for doc in eod_docs:
            data = doc.to_dict()
            user_id = data.get('user_id')
            if user_id:
                all_eod_submitters.add(user_id)
        
        # Get all active users
        users_data = {}
        users_query = firebase_client.db.collection('users').where('status', '==', 'active').stream()
        
        for doc in users_query:
            user_data = doc.to_dict()
            user_id = user_data.get('slack_id')
            
            # Skip if not a valid user
            if not user_id or user_id == 'USLACKBOT':
                continue
            
            # Skip if user has never submitted an EOD report
            if user_id not in all_eod_submitters:
                continue
            
            # Calculate missed days
            missed = 0
            try:
                # Get submissions from the past 30 days (similar to the non-submission report logic)
                thirty_days_ago = today - timedelta(days=30)
                thirty_days_ago_start = datetime.combine(thirty_days_ago, datetime.min.time()).replace(tzinfo=ZoneInfo("America/New_York"))
                thirty_days_ago_start_utc = thirty_days_ago_start.astimezone(ZoneInfo("UTC"))
                
                # Get user's past submissions
                past_submissions = set()
                past_docs = firebase_client.db.collection('eod_reports')\
                    .where('user_id', '==', user_id)\
                    .where('timestamp', '>=', thirty_days_ago_start_utc)\
                    .stream()
                
                for doc in past_docs:
                    doc_data = doc.to_dict()
                    timestamp = doc_data.get('timestamp')
                    if timestamp:
                        # Convert timestamp to NY date
                        submission_date = timestamp.astimezone(ZoneInfo("America/New_York")).date()
                        past_submissions.add(submission_date)
                
                # Calculate consecutive missed days (similar to non-submission report)
                # Start from yesterday and go backwards
                check_date = today - timedelta(days=1)
                consecutive_days = 1  # Today is already missed if not in submitted_on_reporting_day
                
                # If user submitted today, start with 0 consecutive days
                if user_id in submitted_on_reporting_day:
                    consecutive_days = 0
                    
                while consecutive_days > 0:
                    # Skip weekends
                    if check_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
                        check_date = check_date - timedelta(days=1)
                        continue
                    
                    # Check if user submitted on this date
                    if check_date in past_submissions:
                        # Found a submission, stop counting
                        break
                    else:
                        # No submission found, increment counter
                        consecutive_days += 1
                        check_date = check_date - timedelta(days=1)
                        
                        # Limit how far back we check
                        if consecutive_days >= 30 or check_date < thirty_days_ago:
                            break
                
                missed = consecutive_days
                
            except Exception as e:
                logger.error(f"Error calculating missed days for {user_id}: {str(e)}")
            
            # Add user to users_data
            today_status = 'submitted' if user_id in submitted_on_reporting_day else 'missed'
            
            users_data[user_id] = {
                'id': user_id,
                'name': user_data.get('name', 'Unknown'),
                'display_name': user_data.get('display_name', ''),
                'image': user_data.get('image', ''),
                'email': user_data.get('email', ''),
                'title': user_data.get('title', ''),
                'timezone': user_data.get('timezone', 'Unknown'),
                'status': 'active',
                'today_status': today_status,
                'missed_days': missed
            }
        
        return jsonify(users_data)
        
    except Exception as e:
        logger.error(f"Error getting team members: {str(e)}")
        return jsonify({"error": "Failed to load team members"}), 500

@app.route('/api/recent-reports')
def recent_reports():
    """API endpoint to get paginated recent reports"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))  # Increased default limit
        
        # Validate parameters
        if page < 1:
            page = 1
        if limit < 1 or limit > 100:  # Allow up to 100 reports per page
            limit = 20
            
        # Calculate offset
        offset = (page - 1) * limit
        
        # Query reports with pagination
        reports_ref = firebase_client.db.collection('eod_reports')
        
        # Order by timestamp descending (newest first)
        query = reports_ref.order_by('timestamp', direction=firestore.Query.DESCENDING)
        
        # Apply pagination
        query = query.offset(offset).limit(limit + 1)  # Get one extra to check if there are more
        
        # Execute query
        docs = list(query.stream())
        
        # Check if there are more reports
        has_more = len(docs) > limit
        if has_more:
            docs = docs[:limit]  # Remove the extra document
            
        # Process reports
        reports = []
        for doc in docs:
            data = doc.to_dict()
            user_id = data.get('user_id')
            
            # Get user info
            user_name = "Unknown User"
            user_image = ""
            
            try:
                user_doc = firebase_client.db.collection('users').where('slack_id', '==', user_id).limit(1).stream()
                for u_doc in user_doc:
                    user_data = u_doc.to_dict()
                    user_name = user_data.get('name', 'Unknown User')
                    user_image = user_data.get('image', '')
            except Exception as e:
                logger.error(f"Error getting user data: {str(e)}")
            
            timestamp = data.get('timestamp')
            if timestamp:
                if isinstance(timestamp, datetime):
                    created_at = timestamp.astimezone(ZoneInfo("America/New_York")).strftime('%Y-%m-%d %H:%M')
                else:
                    created_at = 'Unknown'
            else:
                created_at = 'Unknown'
            
            # Extract report fields
            short_term = data.get('short_term_projects', '')
            long_term = data.get('long_term_projects', '')
            blockers = data.get('blockers', '')
            next_day_goals = data.get('next_day_goals', '')
            tools_used = data.get('tools_used', '')
            
            # Don't truncate text here, we'll handle it in the frontend
            
            reports.append({
                'id': doc.id,
                'user_id': user_id,
                'user_name': user_name,
                'user_image': user_image,
                'created_at': created_at,
                'short_term_projects': short_term,
                'long_term_projects': long_term,
                'blockers': blockers,
                'next_day_goals': next_day_goals,
                'tools_used': tools_used
            })
        
        return jsonify({
            'reports': reports,
            'page': page,
            'limit': limit,
            'has_more': has_more
        })
        
    except Exception as e:
        logger.error(f"Error in recent_reports API: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/report/<report_id>')
def get_report_detail(report_id):
    """API endpoint to get a single report by ID"""
    try:
        # Get the report document
        doc_ref = firebase_client.db.collection('eod_reports').document(report_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return jsonify({'error': 'Report not found'}), 404
            
        data = doc.to_dict()
        user_id = data.get('user_id')
        
        # Get user info
        user_name = "Unknown User"
        user_image = ""
        user_title = ""
        
        try:
            user_doc = firebase_client.db.collection('users').where('slack_id', '==', user_id).limit(1).stream()
            for u_doc in user_doc:
                user_data = u_doc.to_dict()
                user_name = user_data.get('name', 'Unknown User')
                user_image = user_data.get('image', '')
                user_title = user_data.get('title', '')
        except Exception as e:
            logger.error(f"Error getting user data: {str(e)}")
        
        timestamp = data.get('timestamp')
        if timestamp:
            if isinstance(timestamp, datetime):
                created_at = timestamp.astimezone(ZoneInfo("America/New_York")).strftime('%Y-%m-%d %H:%M')
                date = timestamp.astimezone(ZoneInfo("America/New_York")).strftime('%Y-%m-%d')
                time = timestamp.astimezone(ZoneInfo("America/New_York")).strftime('%H:%M:%S')
            else:
                created_at = 'Unknown'
                date = 'Unknown'
                time = 'Unknown'
        else:
            created_at = 'Unknown'
            date = 'Unknown'
            time = 'Unknown'
        
        report_data = {
            'id': doc.id,
            'user_id': user_id,
            'user_name': user_name,
            'user_image': user_image,
            'user_title': user_title,
            'created_at': created_at,
            'date': date,
            'time': time,
            'short_term_projects': data.get('short_term_projects', ''),
            'long_term_projects': data.get('long_term_projects', ''),
            'blockers': data.get('blockers', ''),
            'next_day_goals': data.get('next_day_goals', ''),
            'tools_used': data.get('tools_used', ''),
            'help_needed': data.get('help_needed', ''),
            'client_feedback': data.get('client_feedback', '')
        }
        
        return jsonify(report_data)
        
    except Exception as e:
        logger.error(f"Error getting report detail: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/missed-submissions/<int:days>')
def api_missed_submissions(days=30):
    """API endpoint to get missed submissions data asynchronously"""
    try:
        # Default to 30 days if not specified
        days = min(max(days, 1), 90)  # Limit between 1 and 90 days
        
        # Get today's date in NY timezone
        now = datetime.now(ZoneInfo("America/New_York"))
        today = now.date()
        
        # Calculate the start date
        start_date = today - timedelta(days=days)
        
        # Get all active users
        users_data = {}
        users_query = firebase_client.db.collection('users').where('status', '==', 'active').stream()
        
        for doc in users_query:
            user_data = doc.to_dict()
            user_id = user_data.get('slack_id')
            
            # Skip if not a valid user
            if not user_id or user_id == 'USLACKBOT':
                continue
            
            # Initialize SlackBot for user profile data
            slack_bot = SlackBot()
            slack_bot.client.token = Config.SLACK_BOT_TOKEN
            
            # Get current year
            current_year = today.year
            
            # Get user's submission calendar for the current year
            submission_calendar = slack_bot.get_user_submission_calendar(user_id, current_year)
            
            # Find the first submission date
            first_submission_date = None
            if submission_calendar:
                # Sort dates and get the earliest one
                sorted_dates = sorted(submission_calendar.keys())
                if sorted_dates:
                    first_submission_date = sorted_dates[0]
            
            # If no submissions yet, skip this user
            if not first_submission_date:
                continue
                
            # Convert to date object
            first_submission_date = datetime.fromisoformat(first_submission_date).date()
            
            # Get all weekdays in the current year up to today
            all_weekdays = []
            year_start = datetime(current_year, 1, 1).date()
            current_date = year_start
            
            while current_date <= today:
                # Only include weekdays
                if current_date.weekday() < 5:  # 0-4 are weekdays (Monday-Friday)
                    all_weekdays.append(current_date)
                current_date += timedelta(days=1)
            
            # Calculate missed dates (all weekdays where the user didn't submit)
            missed_dates = []
            for date in all_weekdays:
                date_str = date.isoformat()
                if date_str not in submission_calendar:
                    missed_dates.append(date)
            
            # Filter missed dates to only include those after first submission and before today
            filtered_missed_dates = [date for date in missed_dates 
                                    if date >= first_submission_date and date <= today]
            
            # Further filter to only include dates within the requested range
            range_filtered_dates = [date for date in filtered_missed_dates 
                                   if date >= start_date]
            
            # Skip users with no missed submissions in the range
            if not range_filtered_dates:
                continue
            
            # Calculate consecutive missed days
            consecutive = 0
            check_date = today
            
            while check_date >= start_date:
                # Skip weekends
                if check_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
                    check_date -= timedelta(days=1)
                    continue
                
                date_str = check_date.isoformat()
                if date_str not in submission_calendar and check_date >= first_submission_date:
                    consecutive += 1
                    check_date -= timedelta(days=1)
                else:
                    break
            
            # Add user to the result
            users_data[user_id] = {
                'id': user_id,
                'name': user_data.get('name', 'Unknown'),
                'image': user_data.get('image', ''),
                'email': user_data.get('email', ''),
                'title': user_data.get('title', ''),
                'dates': [date.strftime('%Y-%m-%d') for date in range_filtered_dates],
                'consecutive': consecutive,
                'first_submission': first_submission_date.isoformat(),
                'total_missed': len(filtered_missed_dates),  # Total missed for the year
                'range_missed': len(range_filtered_dates)    # Missed in the selected range
            }
        
        return jsonify(users_data)
        
    except Exception as e:
        logger.error(f"Error getting missed submissions data: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        try:
            # Initialize internal users
            initialize_internal_users()
            
            # Import setup_scheduler at the top level of the file
            from scheduler import setup_scheduler
            
            # Set up scheduler
            scheduler = setup_scheduler(app)
            
            # Get port from environment variable or default to 3000
            port = int(os.environ.get('PORT', 3000))
            
            # Verify critical configurations
            if not Config.SLACK_SIGNING_SECRET:
                logger.error("Missing SLACK_SIGNING_SECRET configuration")
                raise ValueError("SLACK_SIGNING_SECRET must be configured")
                
            if not Config.SLACK_BOT_TOKEN:
                logger.error("Missing SLACK_BOT_TOKEN configuration")
                raise ValueError("SLACK_BOT_TOKEN must be configured")
            
            # Start the server
            logger.info(f"Starting Flask server on port {port}...")
            app.run(
                host='0.0.0.0',  # Allow external access
                port=port,
                debug=True,      # Enable debug mode for auto-reloading
                use_reloader=True # Explicitly enable reloader
            )
        except Exception as e:
            logger.error(f"Failed to start application: {str(e)}")
            raise