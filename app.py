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
    app = Flask(__name__)
    app.secret_key = Config.FLASK_SECRET_KEY
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    
    return app

app = create_app()

# Initialize Slack bot and Firebase client
slack_bot = SlackBot()
firebase_client = FirebaseClient()

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
    reports = firebase_client.get_recent_reports()
    return render_template('dashboard.html', reports=reports)

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
        text = event.get('text')
        
        # Parse and save report to Firebase
        report_data = {
            'user_id': user_id,
            'text': text,
            'timestamp': datetime.now().isoformat()
        }
        
        report_id = firebase_client.save_eod_report(user_id, report_data)
        if report_id:
            slack_bot.post_report_to_channel(report_data)
            
    except Exception as e:
        logger.error(f"Error processing submission: {str(e)}")
        slack_bot.send_error_message(event.get('user'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        from scheduler import setup_scheduler
        setup_scheduler(app)
    app.run(host='0.0.0.0', port=5000, debug=True)