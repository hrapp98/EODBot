import logging
from flask import Blueprint, request, jsonify
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from app import db
from models import Contractor, EODReport, SubmissionTracker
from .messages import create_eod_prompt, format_report_message

slack_bp = Blueprint('slack', __name__)
logger = logging.getLogger(__name__)

# Initialize Slack client
slack_client = WebClient(token="YOUR_SLACK_BOT_TOKEN")

@slack_bp.route('/slack/events', methods=['POST'])
def slack_events():
    data = request.json
    
    # Verify Slack challenge
    if data.get('type') == 'url_verification':
        return jsonify({'challenge': data.get('challenge')})
    
    # Handle events
    if data.get('type') == 'event_callback':
        event = data.get('event', {})
        if event.get('type') == 'message':
            handle_message(event)
    
    return jsonify({'status': 'ok'})

def handle_message(event):
    """Handle incoming Slack messages"""
    try:
        user_id = event.get('user')
        channel = event.get('channel')
        text = event.get('text', '').lower()
        
        # Handle EOD report submission
        if text.startswith('eod'):
            handle_eod_submission(user_id, channel, text)
        
        # Handle help command
        elif text == 'help':
            send_help_message(channel)
            
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        send_error_message(channel)

def handle_eod_submission(user_id, channel, text):
    """Process EOD report submission"""
    try:
        contractor = Contractor.query.filter_by(slack_id=user_id).first()
        if not contractor:
            contractor = create_new_contractor(user_id)
            
        # Parse EOD report content
        report = parse_eod_report(text)
        
        # Create new report
        new_report = EODReport(
            contractor_id=contractor.id,
            **report
        )
        db.session.add(new_report)
        
        # Update submission tracker
        update_submission_tracker(contractor.id)
        
        db.session.commit()
        
        # Send confirmation
        slack_client.chat_postMessage(
            channel=channel,
            text="Thanks! Your EOD report has been submitted successfully."
        )
        
    except Exception as e:
        logger.error(f"Error processing EOD submission: {e}")
        send_error_message(channel)

def create_new_contractor(slack_id):
    """Create a new contractor record"""
    try:
        user_info = slack_client.users_info(user=slack_id)
        name = user_info['user']['real_name']
        contractor = Contractor(
            slack_id=slack_id,
            name=name
        )
        db.session.add(contractor)
        db.session.commit()
        return contractor
    except SlackApiError as e:
        logger.error(f"Error creating contractor: {e}")
        raise

def parse_eod_report(text):
    """Parse EOD report text into structured data"""
    # Simple parsing logic - can be enhanced based on needs
    lines = text.split('\n')
    report = {
        'short_term_work': '',
        'long_term_work': '',
        'short_term_progress': 0,
        'long_term_progress': 0,
        'accomplishments': '',
        'blockers': '',
        'next_day_goals': '',
        'client_interactions': ''
    }
    
    current_field = None
    for line in lines[1:]:  # Skip 'eod' command
        line = line.strip()
        if not line:
            continue
            
        # Basic parsing logic
        if 'short term:' in line.lower():
            current_field = 'short_term_work'
        elif 'long term:' in line.lower():
            current_field = 'long_term_work'
        elif 'accomplishments:' in line.lower():
            current_field = 'accomplishments'
        elif 'blockers:' in line.lower():
            current_field = 'blockers'
        elif 'goals:' in line.lower():
            current_field = 'next_day_goals'
        elif 'client:' in line.lower():
            current_field = 'client_interactions'
        elif current_field:
            report[current_field] += line + '\n'
            
    return report

def send_error_message(channel):
    """Send error message to Slack"""
    slack_client.chat_postMessage(
        channel=channel,
        text="Sorry, there was an error processing your request. Please try again or contact support."
    )

def send_help_message(channel):
    """Send help message to Slack"""
    help_text = """
*EOD Report Bot Help*
Submit your EOD report using the following format:
