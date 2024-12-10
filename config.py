import os
from datetime import timedelta

class Config:
    # Flask
    FLASK_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key')
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    
    # Slack
    SLACK_CLIENT_ID = os.environ.get('SLACK_CLIENT_ID')
    SLACK_CLIENT_SECRET = os.environ.get('SLACK_CLIENT_SECRET')
    SLACK_SIGNING_SECRET = os.environ.get('SLACK_SIGNING_SECRET')
    SLACK_APP_ID = os.environ.get('SLACK_APP_ID')
    SLACK_BOT_OAUTH_TOKEN = os.environ.get('SLACK_BOT_OAUTH_TOKEN')
    SLACK_EOD_CHANNEL = "eod-reports"
    
    # Schedule settings
    EOD_REMINDER_TIME = "17:00"
    FINAL_REMINDER_TIME = "17:30"
    WEEKLY_SUMMARY_TIME = "17:00"
    WEEKLY_SUMMARY_DAY = "friday"
    
    # Reminder settings
    REMINDER_INTERVAL = timedelta(minutes=30)
    MAX_REMINDERS = 2
    
    # Google Sheets
    SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
    SUBMISSIONS_SHEET = "EOD Submissions"
    TRACKER_SHEET = "Submission Tracker"
