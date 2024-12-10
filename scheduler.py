from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import logging
from models import EODReport
from sheets_client import SheetsClient
from config import Config

logger = logging.getLogger(__name__)

def setup_scheduler(app):
    """Initialize and start the scheduler"""
    scheduler = BackgroundScheduler()
    
    # Schedule EOD prompts
    scheduler.add_job(
        send_eod_prompts,
        CronTrigger(hour=Config.EOD_REMINDER_TIME.split(':')[0], 
                    minute=Config.EOD_REMINDER_TIME.split(':')[1]),
        args=[app],
        id='send_eod_prompts'
    )
    
    # Schedule reminders
    scheduler.add_job(
        send_reminders,
        CronTrigger(hour=Config.FINAL_REMINDER_TIME.split(':')[0], 
                    minute=Config.FINAL_REMINDER_TIME.split(':')[1]),
        args=[app],
        id='send_reminders'
    )
    
    # Schedule weekly summary
    scheduler.add_job(
        generate_weekly_summary,
        CronTrigger(day_of_week=Config.WEEKLY_SUMMARY_DAY,
                    hour=Config.WEEKLY_SUMMARY_TIME.split(':')[0],
                    minute=Config.WEEKLY_SUMMARY_TIME.split(':')[1]),
        args=[app],
        id='generate_weekly_summary'
    )
    
    # Schedule sheets sync
    scheduler.add_job(
        sync_to_sheets,
        CronTrigger(minute='*/15'),  # Every 15 minutes
        args=[app],
        id='sync_to_sheets'
    )
    
    scheduler.start()
    return scheduler

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
        from app import slack_bot
        active_users = get_active_users()
        end_date = datetime.utcnow()
        start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get users who submitted today from Firebase
        try:
            from app import firebase_client
            if firebase_client:
                submitted_users = firebase_client.get_missing_reports(start_date)
            else:
                logger.warning("Firebase client not initialized, cannot check submissions")
                submitted_users = set()
        except Exception as e:
            logger.error(f"Error getting submitted users: {str(e)}")
            submitted_users = set()
        
        # Send reminders to users who haven't submitted
        for user_id in active_users:
            if user_id not in submitted_users:
                slack_bot.send_reminder(user_id)
                
                # Update submission tracker in Firebase
                tracker = SubmissionTracker(
                    user_id=user_id,
                    date=datetime.utcnow().date(),
                    reminder_count=1
                )
                
                if firebase_client:
                    try:
                        firebase_client.save_tracker(tracker.to_dict())
                    except Exception as e:
                        logger.error(f"Failed to save tracker to Firebase: {str(e)}")

def sync_to_sheets(app):
    """Sync reports to Google Sheets"""
    with app.app_context():
        sheets_client = SheetsClient()
        
        # Get today's reports
        start_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            from app import firebase_client
            if firebase_client:
                # Get reports from Firebase
                reports = []
                docs = firebase_client.db.collection('eod_reports')\
                    .where('timestamp', '>=', start_date)\
                    .stream()
                
                for doc in docs:
                    data = doc.to_dict()
                    report = EODReport(
                        user_id=data['user_id'],
                        short_term_projects=data.get('short_term_projects', {}),
                        long_term_projects=data.get('long_term_projects', {}),
                        accomplishments=data.get('accomplishments', ''),
                        blockers=data.get('blockers', ''),
                        next_day_goals=data.get('next_day_goals', ''),
                        client_interactions=data.get('client_interactions', '')
                    )
                    reports.append(report)
                
                # Update sheets
                if reports:
                    sheets_client.update_submissions(reports)
                    sheets_client.update_tracker()
            else:
                logger.warning("Firebase client not initialized, cannot sync reports")
        except Exception as e:
            logger.error(f"Error syncing reports: {str(e)}")

def generate_weekly_summary(app):
    """Generate weekly summary of EOD reports"""
    with app.app_context():
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)
        
        # Get reports for the past week from Firebase
        try:
            from app import firebase_client
            if not firebase_client:
                logger.warning("Firebase client not initialized, cannot generate weekly summary")
                return
                
            reports = []
            docs = firebase_client.db.collection('eod_reports')\
                .where('timestamp', '>=', start_date)\
                .where('timestamp', '<=', end_date)\
                .stream()
            
            for doc in docs:
                data = doc.to_dict()
                report = EODReport(
                    user_id=data['user_id'],
                    short_term_projects=data.get('short_term_projects', {}),
                    long_term_projects=data.get('long_term_projects', {}),
                    accomplishments=data.get('accomplishments', ''),
                    blockers=data.get('blockers', ''),
                    next_day_goals=data.get('next_day_goals', ''),
                    client_interactions=data.get('client_interactions', '')
                )
                reports.append(report)
                
            if not reports:
                logger.info("No reports found for weekly summary")
                return
        except Exception as e:
            logger.error(f"Error getting weekly reports: {str(e)}")
            return
            
        # Group reports by user
        user_reports = {}
        for report in reports:
            if report.user_id not in user_reports:
                user_reports[report.user_id] = []
            user_reports[report.user_id].append(report)
        
        # Generate and post summaries
        from app import slack_bot
        for user_id, user_report_list in user_reports.items():
            summary = _generate_user_summary(user_id, user_report_list)
            slack_bot.send_message(user_id, f"*Weekly Summary*\n{summary}")

def _generate_user_summary(user_id, reports):
    """Generate summary for a single user's reports"""
    # This is a simple summary. In the future, we can use OpenAI to generate better summaries
    total_reports = len(reports)
    completed_reports = sum(1 for r in reports if r.submitted)
    
    summary = f"""
User: <@{user_id}>
Reports Submitted: {completed_reports}/{total_reports}
Key Accomplishments:
{_format_accomplishments(reports)}

Ongoing Projects:
{_format_projects(reports)}
    """.strip()
    
    return summary

def _format_accomplishments(reports):
    accomplishments = []
    for report in reports:
        if report.accomplishments:
            accomplishments.append(f"• {report.accomplishments}")
    return "\n".join(accomplishments) if accomplishments else "None reported"

def _format_projects(reports):
    projects = set()
    for report in reports:
        if report.short_term_projects:
            projects.update(report.short_term_projects.values())
        if report.long_term_projects:
            projects.update(report.long_term_projects.values())
    return "\n".join(f"• {project}" for project in projects) if projects else "None reported"

def get_active_users():
    """Get list of active users"""
    # This should be implemented based on your user management system
    # For now, return a test user
    return ["U12345"]
