from flask import Flask, request, jsonify, render_template
import logging
import os

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

import os
from flask import Flask, request, jsonify, render_template
import logging
from slack_bot import SlackBot
from firebase_client import FirebaseClient
from firebase_admin import firestore
from datetime import datetime
import hmac
import hashlib
from config import Config

# Set up logging with more detailed formatting
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def setup_logging_middleware(app):
    """Configure logging middleware for request tracking"""
    @app.before_request
    def before_request_logging():
        logger.debug(f"Incoming {request.method} request to {request.path}")
        if request.json:
            logger.debug(f"Request payload: {request.json}")

    @app.after_request
    def after_request_logging(response):
        logger.debug(f"Request completed with status {response.status_code}")
        return response

def create_app():
    try:
        logger.info("Creating Flask application...")
        app = Flask(__name__)
        app.secret_key = Config.FLASK_SECRET_KEY
        
        # Set up logging middleware
        setup_logging_middleware(app)
        
        logger.info("Application creation successful")
        return app
    except Exception as e:
        logger.error(f"Failed to create application: {str(e)}")
        raise

app = create_app()

# Initialize clients
slack_bot = SlackBot()
firebase_client = None

# Attempt to initialize Firebase client if credentials are available
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
else:
    missing_vars = [var for var in ['FIREBASE_API_KEY', 'FIREBASE_APP_ID', 'FIREBASE_PROJECT_ID'] 
                   if not getattr(Config, var)]
    logger.warning(f"Firebase configuration incomplete. Missing: {', '.join(missing_vars)}")

def verify_slack_request(request):
    """Verify that the request actually came from Slack"""
    timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
    signature = request.headers.get('X-Slack-Signature', '')
    
    if abs(datetime.now().timestamp() - float(timestamp)) > 60 * 5:
        return False
        
    sig_basestring = f'v0:{timestamp}:{request.get_data(as_text=True)}'
    my_signature = f'v0={hmac.new(Config.SLACK_SIGNING_SECRET.encode(), sig_basestring.encode(), hashlib.sha256).hexdigest()}'
    
    return hmac.compare_digest(my_signature, signature)

@app.route('/slack/events', methods=['POST'])
def slack_events():
    """Handle Slack events"""
    if not verify_slack_request(request):
        return jsonify({'error': 'Invalid request'}), 403

    data = request.json
    
    if data.get('type') == 'url_verification':
        return jsonify({'challenge': data['challenge']})
    
    if data.get('type') == 'event_callback':
        event = data.get('event', {})
        
        if event.get('type') == 'message' and 'bot_id' not in event:
            handle_message(event)
        elif event.get('type') == 'app_mention':
            handle_app_mention(event)
            
    return jsonify({'status': 'ok'})
# Slack event handlers
import time
import hmac
import hashlib
from datetime import datetime
from google.cloud import firestore

@app.route('/slack/events', methods=['POST'])
def handle_slack_events():
    """Handle Slack events and commands"""
    try:
        # Verify request signature
        timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
        signature = request.headers.get('X-Slack-Signature', '')
        
        # Verify the request
        if not verify_slack_request(timestamp, signature, request.get_data()):
            logger.warning("Invalid Slack request signature")
            return jsonify({'error': 'invalid_signature'}), 401
        
        # Parse the event data
        data = request.json
        
        # Handle URL verification
        if data.get('type') == 'url_verification':
            return jsonify({'challenge': data['challenge']})
            
        # Handle events
        if data.get('type') == 'event_callback':
            event = data.get('event', {})
            event_type = event.get('type')
            
            if event_type == 'message':
                handle_message(event)
            elif event_type == 'app_mention':
                handle_app_mention(event)
                
        return jsonify({'status': 'ok'})
        
    except Exception as e:
        logger.error(f"Error handling Slack event: {str(e)}")
        return jsonify({'error': 'internal_error'}), 500

def verify_slack_request(timestamp, signature, body):
    """Verify Slack request signature"""
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False
        
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    my_signature = 'v0=' + hmac.new(
        Config.SLACK_SIGNING_SECRET.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(my_signature, signature)

@app.route('/', methods=['GET'])
def index():
    """Show welcome page"""
    if request.headers.get('Accept') == 'application/json':
        return jsonify({'status': 'ok'})
    return render_template('index.html')

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

def handle_message(event):
    """Process incoming messages"""
    try:
        text = event.get('text', '').lower()
        user_id = event.get('user')
        
        if 'eod report' in text:
            slack_bot.send_eod_prompt(user_id)
        elif text.startswith('submit eod:'):
            handle_eod_submission(event)
            
    except Exception as e:
        logger.error(f"Error handling message: {str(e)}")

def handle_app_mention(event):
    """Handle when the bot is mentioned"""
    try:
        text = event.get('text', '').lower()
        user_id = event.get('user')
        
        if 'status' in text:
            slack_bot.send_status_update(user_id)
        elif 'help' in text:
            slack_bot.send_help_message(user_id)
            
    except Exception as e:
        logger.error(f"Error handling mention: {str(e)}")

def handle_eod_submission(event):
    """Process EOD report submission"""
    try:
        user_id = event.get('user')
        text = event.get('text').replace('submit eod:', '', 1).strip()
        
        # Create and save EOD report
        from models import EODReport
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