from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from models import EODReport, SubmissionTracker
from extensions import db
from sheets_client import SheetsClient
from config import Config
import logging

logger = logging.getLogger(__name__)

def setup_scheduler(app):
    """Initialize and configure the scheduler"""
    scheduler = BackgroundScheduler()
    
    with app.app_context():
        # Schedule EOD prompts
        scheduler.add_job(
            send_eod_prompts,
            CronTrigger.from_crontab(f"0 17 * * 1-5"),  # 5 PM weekdays
            args=[app]
        )
        
        # Schedule reminders
        scheduler.add_job(
            send_reminders,
            CronTrigger.from_crontab(f"30 17 * * 1-5"),  # 5:30 PM weekdays
            args=[app]
        )
        
        # Schedule weekly summary
        scheduler.add_job(
            generate_weekly_summary,
            CronTrigger.from_crontab(f"0 17 * * 5"),  # 5 PM Fridays
            args=[app]
        )
        
        # Schedule sheets sync
        scheduler.add_job(
            sync_to_sheets,
            'interval',
            minutes=15,
            args=[app]
        )
    
    scheduler.start()
    return scheduler

def send_eod_prompts(app):
    """Send initial EOD prompts to all users"""
    from app import slack_bot
    
    with app.app_context():
        # In production, get this from your user management system
        active_users = get_active_users()
        
        for user_id in active_users:
            try:
                slack_bot.send_eod_prompt(user_id)
                
                # Create tracker entry
                tracker = SubmissionTracker(
                    user_id=user_id,
                    date=datetime.utcnow().date()
                )
                db.session.add(tracker)
                
            except Exception as e:
                logger.error(f"Error sending prompt to {user_id}: {str(e)}")
        
        db.session.commit()

def send_reminders(app):
    """Send reminders to users who haven't submitted"""
    from app import slack_bot, db
    
    with app.app_context():
        today = datetime.utcnow().date()
        
        # Get users who haven't submitted
        missing_submissions = SubmissionTracker.query.filter_by(
            date=today,
            submitted=False
        ).all()
        
        for tracker in missing_submissions:
            try:
                if tracker.reminder_count < Config.MAX_REMINDERS:
                    slack_bot.send_reminder(tracker.user_id)
                    tracker.reminder_count += 1
                    
            except Exception as e:
                logger.error(f"Error sending reminder to {tracker.user_id}: {str(e)}")
        
        db.session.commit()

def sync_to_sheets(app):
    """Sync recent submissions to Google Sheets"""
    with app.app_context():
        sheets_client = SheetsClient()
        
        # Sync last 24 hours of submissions
        since = datetime.utcnow() - timedelta(days=1)
        reports = EODReport.query.filter(
            EODReport.created_at >= since
        ).order_by(EODReport.created_at.desc()).all()
        
        sheets_client.update_submissions(reports)
        sheets_client.update_tracker()

def get_active_users():
    """Get list of active users"""
    # This should be implemented based on your user management system
    # For now, return a test user
    return ["U12345"]
