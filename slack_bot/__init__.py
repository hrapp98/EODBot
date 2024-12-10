"""
Slack Bot package for EOD report management.
This package handles Slack interactions, message formatting, and event handling.
"""

import os
import logging
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Slack client with token from environment
SLACK_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
if not SLACK_TOKEN:
    logger.warning("SLACK_BOT_TOKEN not found in environment variables!")

try:
    slack_client = WebClient(token=SLACK_TOKEN)
    
    # Test the connection
    auth_test = slack_client.auth_test()
    bot_id = auth_test["bot_id"]
    bot_user_id = auth_test["user_id"]
    
    logger.info(f"Slack bot initialized. Bot ID: {bot_id}")
    
except SlackApiError as e:
    logger.error(f"Error initializing Slack client: {e.response['error']}")
    slack_client = None
    bot_id = None
    bot_user_id = None

# Export constants and utilities
SLACK_EVENTS_PATH = '/slack/events'
DEFAULT_REMINDER_CHANNEL = '#eod-reports'
MANAGEMENT_CHANNEL = '#management'

def is_bot_message(event):
    """Check if a message event came from our bot"""
    return event.get('bot_id') == bot_id or event.get('user') == bot_user_id

def get_channel_id(channel_name):
    """Get channel ID from channel name"""
    try:
        if slack_client:
            response = slack_client.conversations_list()
            for channel in response['channels']:
                if channel['name'] == channel_name.lstrip('#'):
                    return channel['id']
    except SlackApiError as e:
        logger.error(f"Error getting channel ID: {e.response['error']}")
    return None

# Initialize package-level variables
VERSION = '1.0.0'
AUTHOR = 'EOD Report Bot'
