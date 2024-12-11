import hmac
import hashlib
import json
import os
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from slack_bot import SlackBot
from firebase_client import FirebaseClient
from config import Config
from models import EODReport, SubmissionTracker
import logging

# Setup logging with more detailed formatting
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Set up logging with more detailed formatting
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

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
        
        logger.debug(f"Processing message from user {user_id}: {text}")
        
        if text == 'eod report':
            # Send EOD report prompt
            slack_bot.send_eod_prompt(user_id)
        elif text.startswith('submit eod:'):
            # Handle EOD submission
            handle_eod_submission(event)
        elif text == 'status':
            # Check submission status
            slack_bot.send_status_update(user_id)
        elif text == 'help':
            # Send help message
            slack_bot.send_help_message(user_id)
            
    except Exception as e:
        logger.error(f"Error handling message: {str(e)}")
        slack_bot.send_error_message(user_id)

def handle_app_mention(event):
    """Handle when the bot is mentioned"""
    try:
        text = event.get('text', '').lower().replace(f'<@{event.get("bot_id", "")}>', '').strip()
        user_id = event.get('user')
        
        logger.debug(f"Processing mention from user {user_id}: {text}")
        
        if 'eod report' in text:
            slack_bot.send_eod_prompt(user_id)
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
        logger.info("Received Slack command request")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"Form data: {dict(request.form)}")
        logger.debug(f"Request method: {request.method}")
        logger.debug(f"Content type: {request.content_type}")
        logger.debug(f"Content length: {request.content_length}")
        
        # Get the raw body for signature verification
        raw_body = request.get_data(as_text=True)
        logger.debug(f"Raw request body: {raw_body}")
        
        # Verify request signature
        timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
        signature = request.headers.get('X-Slack-Signature', '')
        
        logger.debug(f"Verifying Slack request - Timestamp: {timestamp}, Signature: {signature}")
        
        if not timestamp or not signature:
            logger.error("Missing required Slack headers")
            return jsonify({'error': 'missing_headers'}), 400
            
        # Verify timestamp
        try:
            current_ts = datetime.now().timestamp()
            timestamp_age = abs(current_ts - float(timestamp))
            logger.debug(f"Current timestamp: {current_ts}")
            logger.debug(f"Request timestamp age: {timestamp_age} seconds")
            
            if timestamp_age > 60 * 5:
                logger.warning(f"Request timestamp too old: {timestamp_age} seconds")
                return jsonify({'error': 'invalid_timestamp'}), 403
        except ValueError as e:
            logger.error(f"Error parsing timestamp: {str(e)}")
            return jsonify({'error': 'invalid_timestamp_format'}), 400
            
        # Calculate signature
        sig_basestring = f"v0:{timestamp}:{raw_body}"
        logger.debug(f"Signature base string: {sig_basestring}")
        
        try:
            my_signature = 'v0=' + hmac.new(
                Config.SLACK_SIGNING_SECRET.encode(),
                sig_basestring.encode(),
                hashlib.sha256
            ).hexdigest()
            
            logger.debug(f"Calculated signature: {my_signature}")
            logger.debug(f"Received signature: {signature}")
            
            if not hmac.compare_digest(my_signature, signature):
                logger.warning("Signature verification failed")
                return jsonify({'error': 'invalid_signature'}), 403
                
            logger.info("Signature verification successful")
                
        except Exception as e:
            logger.error(f"Error calculating signature: {str(e)}")
            return jsonify({'error': 'signature_calculation_failed'}), 500

        # Parse form data
        if not request.form:
            logger.warning("No form data in slash command request")
            return jsonify({'error': 'missing_data'}), 400
            
        command = request.form.get('command', '')
        user_id = request.form.get('user_id', '')
        
        logger.debug(f"Received slash command: {command} from user: {user_id}")
        
        if command == '/eod':
            # Send EOD prompt
            slack_bot.send_eod_prompt(user_id)
            return jsonify({
                'response_type': 'ephemeral',
                'text': 'Please check your DM for the EOD report prompt!'
            })
            
        return jsonify({
            'response_type': 'ephemeral',
            'text': 'Unknown command'
        })
        
    except Exception as e:
        logger.error(f"Error handling slash command: {str(e)}")
        return jsonify({
            'response_type': 'ephemeral',
            'text': 'Sorry, there was an error processing your command.'
        }), 500

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
            
            logger.info("Starting Flask server...")
            app.run(host='0.0.0.0', port=5000, debug=True)
        except Exception as e:
            logger.error(f"Failed to start application: {str(e)}")
            raise