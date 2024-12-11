import os
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class Config:
    # Flask
    FLASK_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key')
    
    # Firebase Configuration
    FIREBASE_API_KEY = os.environ.get('FIREBASE_API_KEY')  # Private key ID
    FIREBASE_PROJECT_ID = os.environ.get('FIREBASE_PROJECT_ID')
    FIREBASE_PRIVATE_KEY = os.environ.get('FIREBASE_PRIVATE_KEY')  # Complete private key with headers
    FIREBASE_CLIENT_EMAIL = os.environ.get('FIREBASE_CLIENT_EMAIL')  # Service account email
    
    @classmethod
    def firebase_config_valid(cls):
        """Check if Firebase configuration is complete"""
        return all([
            cls.FIREBASE_API_KEY,
            cls.FIREBASE_PROJECT_ID,
            cls.FIREBASE_PRIVATE_KEY,
            cls.FIREBASE_CLIENT_EMAIL
        ])
    
    # Slack
    SLACK_CLIENT_ID = os.environ.get('SLACK_CLIENT_ID')
    SLACK_CLIENT_SECRET = os.environ.get('SLACK_CLIENT_SECRET')
    SLACK_BOT_OAUTH_TOKEN = os.environ.get('SLACK_BOT_OAUTH_TOKEN')
    SLACK_BOT_TOKEN = SLACK_BOT_OAUTH_TOKEN
    SLACK_SIGNING_SECRET = os.environ.get('SLACK_SIGNING_SECRET')
    SLACK_APP_ID = os.environ.get('SLACK_APP_ID')
    SLACK_CHANNEL = os.environ.get('SLACK_CHANNEL', 'eod-reports')
    SLACK_WEEKLY_SUMMARY_CHANNEL = os.environ.get('SLACK_WEEKLY_SUMMARY_CHANNEL', 'weekly-progress-summaries')
    
    # Schedule settings (Eastern Time)
    EOD_REMINDER_TIME = "17:00"  # 5 PM ET
    FINAL_REMINDER_TIME = "17:30"  # 5:30 PM ET
    WEEKLY_SUMMARY_TIME = "17:00"  # 5 PM ET Friday
    WEEKLY_SUMMARY_DAY = "FRI"
    
    # Reminder settings
    REMINDER_INTERVAL = timedelta(minutes=30)
    MAX_REMINDERS = 2
    
    # Google Sheets
    SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
    GOOGLE_SERVICE_ACCOUNT = os.environ.get('GOOGLE_SERVICE_ACCOUNT')  # JSON string of service account credentials
    SUBMISSIONS_SHEET = "EOD Reports"  # Name of the sheet tab
    TRACKER_SHEET = "Submission Tracker"  # Name of the tracker sheet tab
    WEEKLY_SUMMARIES_SHEET = "Weekly Summaries"  # Name of the weekly summaries sheet tab
    
    @classmethod
    def sheets_config_valid(cls):
        """Check if Sheets configuration is complete"""
        return all([
            cls.SHEET_ID,
            cls.GOOGLE_SERVICE_ACCOUNT
        ])
    
    @classmethod
    def slack_config_valid(cls):
        """Check if Slack configuration is complete"""
        return all([
            cls.SLACK_BOT_TOKEN,
            cls.SLACK_SIGNING_SECRET
        ])
    
    # OpenAI Configuration - Move this before the openai_config_valid method
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    
    @classmethod
    def openai_config_valid(cls):
        """Check if OpenAI configuration is complete and valid"""
        # Add debug logging to help diagnose the issue
        logger.debug(f"Checking OpenAI API key validity. Key exists: {bool(cls.OPENAI_API_KEY)}")
        if not cls.OPENAI_API_KEY:
            logger.error("OpenAI API key is not set in environment variables")
            return False
        if not cls.OPENAI_API_KEY.startswith('sk-'):
            logger.error("OpenAI API key appears to be invalid (should start with 'sk-')")
            return False
        logger.info("OpenAI API key is valid")
        return True
    
    # Debug mode - set to False for production
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
