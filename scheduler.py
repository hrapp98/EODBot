from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import logging
from models import EODReport, SubmissionTracker
from sheets_client import SheetsClient
from config import Config
from zoneinfo import ZoneInfo
import traceback

logger = logging.getLogger(__name__)

def setup_scheduler(app):
    """Initialize and start the scheduler"""
    scheduler = BackgroundScheduler()
    
    # EOD Reminder at 5 PM ET
    scheduler.add_job(
        send_eod_prompts,
        CronTrigger(hour=17, minute=0, timezone="America/New_York"),
        args=[app],
        id='eod_prompts'
    )
    
    # Final Reminder at 5:30 PM ET
    scheduler.add_job(
        send_reminders,
        CronTrigger(hour=17, minute=30, timezone="America/New_York"),
        args=[app],
        id='final_reminders'
    )
    
    # Weekly Summary every Friday at 5 PM ET
    scheduler.add_job(
        generate_weekly_summary,
        CronTrigger(day_of_week='fri', hour=17, minute=0, timezone="America/New_York"),
        args=[app],
        id='weekly_summary'
    )
    
    # Remove test reminder job
    # scheduler.add_job(
    #     send_test_reminder,
    #     CronTrigger(minute='*'),
    #     args=[app],
    #     id='test_reminder'
    # )
    
    scheduler.start()
    return scheduler

def send_test_reminder(app):
    """Send test reminder to Harlan"""
    with app.app_context():
        try:
            from app import slack_bot, firebase_client
            user_id = "U083K838X8V"  # Harlan's user ID
            
            # Get date range for today
            now = datetime.now(ZoneInfo("America/New_York"))
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Check for missing submissions
            missing = firebase_client.get_missed_submissions(start, end)
            
            if user_id in missing:
                message = "🔔 This is a test reminder - sent every minute!"
                slack_bot.send_message(user_id, message)
                logger.info(f"Sent test reminder to user {user_id}")
            else:
                logger.info(f"Skipping reminder for {user_id} - submission already received for today")
            
        except Exception as e:
            logger.error(f"Error sending test reminder: {str(e)}")
            logger.error(traceback.format_exc())

def send_eod_prompts(app):
    """Send EOD prompts to all active users"""
    with app.app_context():
        from app import slack_bot
        active_users = get_active_users()
        
        for user_id in active_users:
            slack_bot.send_eod_prompt(user_id)
            
def send_reminders(app):
    """Send reminders to users who haven't submitted reports"""
    with app.app_context():
        try:
            from app import slack_bot, firebase_client
            
            # Get date range for today
            now = datetime.now(ZoneInfo("America/New_York"))
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Get users who missed submissions
            missing = firebase_client.get_missed_submissions(start, end)
            
            for user_id, missed_dates in missing.items():
                # Check if user has multiple missed days
                consecutive_days = len(missed_dates)
                
                # Send appropriate reminder
                if consecutive_days >= 3:
                    # Escalated reminder
                    message = (f"*URGENT REMINDER*\nYou have missed {consecutive_days} consecutive daily reports. "
                             "Please submit your EOD report as soon as possible.")
                    slack_bot.send_message(Config.SLACK_CHANNEL, f"<@{user_id}> has missed {consecutive_days} consecutive reports.")
                elif consecutive_days >= 2:
                    # Warning reminder
                    message = "⚠️ You have missed multiple daily reports. Please submit your EOD report for today."
                else:
                    # Normal reminder
                    message = "Friendly reminder: Please submit your EOD report for today."
                
                # Send reminder to user
                slack_bot.send_message(user_id, message)
                
                # Track reminder
                firebase_client.save_reminder(user_id, 
                    'escalated' if consecutive_days >= 3 else 'warning' if consecutive_days >= 2 else 'daily')
                
                logger.info(f"Sent {'escalated' if consecutive_days >= 3 else 'warning' if consecutive_days >= 2 else 'daily'} "
                          f"reminder to user {user_id}")
                
        except Exception as e:
            logger.error(f"Error sending reminders: {str(e)}")
            logger.error(traceback.format_exc())

def sync_to_sheets(app):
    """Sync reports to Google Sheets"""
    with app.app_context():
        sheets_client = SheetsClient()
        
        # Get today's reports
        start_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            # Create new Firebase client instance
            from firebase_client import FirebaseClient
            from config import Config
            
            firebase_client = None
            if Config.firebase_config_valid():
                firebase_client = FirebaseClient()
            
            if firebase_client and firebase_client.db:
                # Get reports from Firebase
                docs = firebase_client.db.collection('eod_reports')\
                    .where('timestamp', '>=', start_date)\
                    .stream()
                
                # Pass raw report data to sheets client
                for doc in docs:
                    data = doc.to_dict()
                    sheets_client.update_submissions(data)
                
                # Update tracker sheet
                sheets_client.update_tracker()
            else:
                logger.warning("Firebase client not initialized, cannot sync reports")
        except Exception as e:
            logger.error(f"Error syncing reports: {str(e)}")

def generate_weekly_summary(app):
    """Generate weekly summary of EOD reports"""
    with app.app_context():
        end_date = datetime.now(ZoneInfo("America/New_York"))
        start_date = end_date - timedelta(days=7)
        
        try:
            from app import firebase_client, slack_bot, sheets_client
            from openai_client import OpenAIClient
            
            if not Config.openai_config_valid():
                logger.error("OpenAI configuration is not valid. Skipping weekly summary.")
                return
                
            if not firebase_client:
                logger.warning("Firebase client not initialized")
                return
                
            # Get reports for the past week
            reports = firebase_client.get_reports_for_date_range(start_date, end_date)
            if not reports:
                logger.info("No reports found for weekly summary")
                return
            
            try:
                # Initialize OpenAI client
                openai_client = OpenAIClient()
                
                # Group reports by user
                user_reports = {}
                for report in reports:
                    if report['user_id'] not in user_reports:
                        user_reports[report['user_id']] = []
                    user_reports[report['user_id']].append(report)
                
                # Generate and post summaries
                for user_id, user_reports_list in user_reports.items():
                    # Generate summary using OpenAI
                    summary = openai_client.generate_weekly_summary(user_reports_list)
                    
                    # Post to Slack
                    slack_bot.post_weekly_summary(user_id, summary)
                    
                    # Add to Google Sheets
                    if sheets_client and sheets_client.service:
                        try:
                            sheets_client.append_weekly_summary(user_id, summary, start_date, end_date)
                        except Exception as e:
                            logger.error(f"Error updating sheets with weekly summary: {str(e)}")
                    
            except ValueError as ve:
                logger.error(f"OpenAI client initialization error: {str(ve)}")
                return
                
        except Exception as e:
            logger.error(f"Error generating weekly summaries: {str(e)}")

def get_active_users():
    """Get list of active users"""
    # This should be implemented based on your user management system
    # For now, return a test user
    return ["U12345"]
