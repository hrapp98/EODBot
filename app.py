from flask import Flask, request, jsonify, render_template
from datetime import datetime
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
            
        logger.info("Application creation successful")
        return app
    except Exception as e:
        logger.error(f"Failed to create application: {str(e)}")
        raise

app = create_app()

# Initialize clients
slack_bot = SlackBot()
firebase_client = None
sheets_client = None

# Initialize Firebase client if credentials are available
if Config.firebase_config_valid():
    try:
        logger.info("Starting Firebase client initialization...")
        firebase_client = FirebaseClient()
        if firebase_client.db is None:
            logger.warning("Firebase client not properly initialized - Firestore client is None")
        else:
            logger.info("Firebase client initialized successfully with Firestore access")
    except Exception as e:
        logger.error(f"Failed to initialize Firebase client: {str(e)}")
        firebase_client = None

# Initialize Sheets client if credentials are available
if Config.sheets_config_valid():
    try:
        logger.info("Starting Sheets client initialization...")
        sheets_client = SheetsClient()
        if sheets_client.service is None:
            logger.warning("Sheets client not properly initialized")
        else:
            logger.info("Sheets client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Sheets client: {str(e)}")
        sheets_client = None

@app.route('/', methods=['GET'])
def index():
    """Show welcome page"""
    if request.headers.get('Accept') == 'application/json':
        return jsonify({'status': 'ok'})
    return render_template('index.html')

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
            
        # Handle direct messages
        if channel_type == 'im':
            if text == 'eod report':
                # Open EOD report modal
                trigger_id = event.get('trigger_id')
                if trigger_id:
                    # Pass the channel ID in private_metadata
                    private_metadata = json.dumps({'channel_id': channel_id})
                    slack_bot.send_eod_prompt(trigger_id, private_metadata)
                else:
                    slack_bot.send_message(user_id, "Please use the /eod command to submit your report.")
            elif text.startswith('submit eod:'):
                # Handle EOD submission
                handle_eod_submission(event)
            elif text == 'status':
                # Check submission status
                slack_bot.send_status_update(user_id)
            elif text == 'help':
                # Send help message
                slack_bot.send_help_message(user_id)
            else:
                # Try to parse as EOD report
                try:
                    report = EODReport.create_from_text(user_id, text)
                    if firebase_client:
                        firebase_client.save_eod_report(user_id, report.to_dict())
                        slack_bot.post_report_to_channel(report.to_dict())
                        slack_bot.send_message(user_id, "Thank you! Your EOD report has been submitted.")
                except Exception as e:
                    logger.error(f"Error processing EOD report: {str(e)}")
                    slack_bot.send_message(user_id, "I couldn't process that as an EOD report. Try using the format shown in the prompt, or type 'help' for instructions.")
            
    except Exception as e:
        logger.error(f"Error handling message: {str(e)}")
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
                
                # Create a closure to capture the variables
                def create_background_task(user_id, report_data, is_edit, report_id):
                    def background_tasks():
                        try:
                            # Save to Firebase
                            saved_report_id = None
                            if is_edit and report_id:
                                firebase_client.update_eod_report(report_id, report_data)
                                saved_report_id = report_id
                            else:
                                saved_report_id = firebase_client.save_eod_report(user_id, report_data)

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
                                    from scheduler import generate_weekly_summary
                                    generate_weekly_summary(app)
                                    logger.info(f"Generated weekly summary after {action_type} (debug mode)")
                            except Exception as e:
                                logger.error(f"Error generating debug weekly summary: {str(e)}")
                                
                        except Exception as e:
                            logger.error(f"Error in background tasks: {str(e)}")
                            slack_bot.send_message(user_id, "There was an error processing your submission. Please try again or contact support.")

                    return background_tasks

                # Start background tasks in a new thread
                from threading import Thread
                Thread(target=create_background_task(user_id, report_data, is_edit, report_id)).start()
                
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

@app.route('/dashboard')
def dashboard():
    """Render submission status dashboard"""
    try:
        if not firebase_client:
            return "Firebase client not initialized. Please check configuration.", 500
            
        # Get recent reports from Firebase
        reports = []
        docs = firebase_client.db.collection('eod_reports')\
            .order_by('timestamp', direction=firestore.Query.DESCENDING)\
            .limit(10)\
            .stream()
        
        for doc in docs:
            data = doc.to_dict()
            created_at = datetime.fromisoformat(data['timestamp'])
            reports.append({
                'user_id': data['user_id'],
                'created_at': created_at
            })
            
        return render_template('dashboard.html', reports=reports)
    except Exception as e:
        logger.error(f"Error loading dashboard: {str(e)}")
        return "Error loading dashboard. Please check server logs.", 500


if __name__ == '__main__':
    with app.app_context():
        try:
            logger.info("Setting up scheduler...")
            from scheduler import setup_scheduler
            setup_scheduler(app)
            logger.info("Scheduler setup complete")
            
            # Get port from environment variable or default to 5000
            port = int(os.environ.get('PORT', 5000))
            
            logger.info(f"Starting Flask server on port {port}...")
            app.run(host='0.0.0.0', port=port, debug=False)
        except Exception as e:
            logger.error(f"Failed to start application: {str(e)}")
            raise