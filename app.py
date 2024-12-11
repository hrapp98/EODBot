from flask import Flask, request, jsonify, render_template
from slack_sdk.errors import SlackApiError
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
firebase_client = FirebaseClient()

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
                    slack_bot.send_eod_prompt(trigger_id)
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
        
        # Process command
        command = request.form.get('command')
        trigger_id = request.form.get('trigger_id')
        
        if command == '/eod':
            if not trigger_id:
                return jsonify({'error': 'missing_trigger'}), 400
                
            slack_bot.send_eod_prompt(trigger_id)
            return jsonify({
                'response_type': 'ephemeral',
                'text': 'Opening EOD report form...'
            })
            
        return jsonify({
            'response_type': 'ephemeral',
            'text': 'Unknown command'
        })
        
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
        # Verify request is from Slack
        payload = request.json
        if not payload:
            logger.error("Empty payload received")
            return jsonify({'error': 'empty_payload'}), 400
        
        # Handle different interaction types
        interaction_type = payload.get('type')
        logger.info(f"Processing {interaction_type} with payload: {payload}")
        
        if interaction_type == 'view_submission':
            # Handle modal submission
            view = payload.get('view', {})
            if view.get('callback_id') == 'eod_report_modal':
                user_id = payload.get('user', {}).get('id')
                if not user_id:
                    logger.warning("Missing user_id in modal submission")
                    return jsonify({'error': 'missing_user'}), 400
                
                # Extract values from blocks
                state = view.get('state', {}).get('values', {})
                report_data = {
                    'short_term_projects': state.get('short_term_block', {}).get('short_term_input', {}).get('value', ''),
                    'long_term_projects': state.get('long_term_block', {}).get('long_term_input', {}).get('value', ''),
                    'blockers': state.get('blockers_block', {}).get('blockers_input', {}).get('value', ''),
                    'next_day_goals': state.get('goals_block', {}).get('goals_input', {}).get('value', ''),
                    'tools_used': state.get('tools_block', {}).get('tools_input', {}).get('value', ''),
                    'help_needed': state.get('help_block', {}).get('help_input', {}).get('value', ''),
                    'user_id': user_id,
                    'created_at': datetime.utcnow().isoformat()
                }
                
                # Save to Firebase
                if not firebase_client:
                    logger.error("Firebase client not initialized")
                    return jsonify({
                        'response_action': 'errors',
                        'errors': {
                            'short_term_block': 'Service unavailable. Please try again later.'
                        }
                    })

                try:
                    # Save the report
                    doc_id = firebase_client.save_eod_report(user_id, report_data)
                    if not doc_id:
                        raise Exception("Failed to save report")

                    # Post to channel
                    slack_bot.post_report_to_channel(report_data)
                    
                    # Close the modal first
                    response = {'response_action': 'clear'}
                    
                    # Then send confirmation in a separate message
                    slack_bot.send_message(
                        user_id,
                        ":white_check_mark: Your EOD report has been submitted successfully! Thank you for your update."
                    )
                    
                    return jsonify(response)

                except Exception as e:
                    logger.error(f"Error processing EOD submission: {str(e)}")
                    return jsonify({
                        'response_action': 'errors',
                        'errors': {
                            'short_term_block': 'Failed to submit report. Please try again.'
                        }
                    })
                
        elif interaction_type == 'block_actions':
            # Handle button clicks
            for action in payload.get('actions', []):
                if action.get('value') == 'skip_eod':
                    user_id = payload.get('user', {}).get('id')
                    if not user_id:
                        logger.warning("Missing user_id in payload")
                        return jsonify({'error': 'missing_user'}), 400

                    channel_id = payload.get('channel', {}).get('id')
                    if not channel_id:
                        channel_id = payload.get('container', {}).get('channel_id')
                    
                    message_ts = payload.get('message', {}).get('ts')
                    if not message_ts:
                        logger.warning("Missing message timestamp")
                        return jsonify({'error': 'missing_timestamp'}), 400

                    # Mark as skipped in tracker
                    if firebase_client:
                        tracker = EODTracker(
                            user_id=user_id,
                            status='skipped',
                            timestamp=datetime.utcnow().isoformat()
                        )
                        try:
                            firebase_client.save_tracker(tracker.to_dict())
                            logger.info(f"Saved skip tracker for user {user_id}")
                        except Exception as e:
                            logger.error(f"Failed to save tracker: {str(e)}")
                    
                    # Update the original message
                    try:
                        slack_bot.client.chat_update(
                            channel=channel_id,
                            ts=message_ts,
                            blocks=[{
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": ":white_check_mark: *EOD report has been skipped for today.*"
                                }
                            }]
                        )
                        logger.info(f"Updated message for user {user_id}")
                    except Exception as e:
                        logger.error(f"Error updating message: {str(e)}")
                    
                    return jsonify({
                        'response_type': 'ephemeral',
                        'text': 'EOD report skipped for today.'
                    })
        
        return jsonify({'status': 'ok'})
        
    except Exception as e:
        logger.error(f"Error handling interactive component: {str(e)}")
        return jsonify({'error': 'internal_error'}), 500

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