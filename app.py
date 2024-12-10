import os
from flask import Flask, request, jsonify, render_template
import logging
from slack_bot import SlackBot
from firebase_client import FirebaseClient
from datetime import datetime
import hmac
import hashlib
from config import Config
from extensions import db

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def create_app():
    try:
        logger.info("Creating Flask application...")
        app = Flask(__name__)
        app.secret_key = Config.FLASK_SECRET_KEY
        
        # Configure database
        logger.info("Configuring database...")
        if not Config.SQLALCHEMY_DATABASE_URI:
            logger.error("DATABASE_URL environment variable is not set")
            raise ValueError("DATABASE_URL environment variable is not set")
        
        logger.info(f"Database URL format: {Config.SQLALCHEMY_DATABASE_URI.split('@')[0].split(':')[0]}://****")
        app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLALCHEMY_DATABASE_URI
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        # Initialize extensions
        logger.info("Initializing database extension...")
        db.init_app(app)
        
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
if all([
    Config.FIREBASE_API_KEY,
    Config.FIREBASE_APP_ID,
    Config.FIREBASE_PROJECT_ID,
    Config.FIREBASE_STORAGE_BUCKET
]):
    try:
        firebase_client = FirebaseClient()
        logger.info("Firebase client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Firebase client: {str(e)}")
else:
    logger.warning("Firebase configuration incomplete. Some features will be disabled.")

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

@app.route('/dashboard')
def dashboard():
    """Render submission status dashboard"""
    try:
        from models import EODReport
        reports = EODReport.query.order_by(EODReport.created_at.desc()).limit(10).all()
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
        db.session.add(report)
        db.session.commit()
        
        # Post to Slack channel
        slack_bot.post_report_to_channel(report.to_dict())
        slack_bot.send_message(user_id, "Your EOD report has been submitted successfully!")
            
    except Exception as e:
        logger.error(f"Error processing submission: {str(e)}")
        slack_bot.send_error_message(event.get('user'))

if __name__ == '__main__':
    with app.app_context():
        try:
            logger.info("Creating database tables...")
            db.create_all()
            logger.info("Database tables created successfully")
            
            logger.info("Setting up scheduler...")
            from scheduler import setup_scheduler
            setup_scheduler(app)
            logger.info("Scheduler setup complete")
            
            logger.info("Starting Flask server...")
            app.run(host='0.0.0.0', port=5000, debug=True)
        except Exception as e:
            logger.error(f"Failed to start application: {str(e)}")
            raise