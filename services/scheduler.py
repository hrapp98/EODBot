import logging
from datetime import datetime, timedelta
from app import scheduler, db
from models import Contractor, SubmissionTracker
from slack_bot.handlers import slack_client
from slack_bot.messages import create_eod_prompt

logger = logging.getLogger(__name__)

@scheduler.task('cron', id='send_eod_prompts', hour=17)
def send_eod_prompts():
    """Send EOD prompts to all contractors at their local 5 PM"""
    try:
        contractors = Contractor.query.all()
        for contractor in contractors:
            # Send EOD prompt
            prompt = create_eod_prompt()
            slack_client.chat_postMessage(
                channel=contractor.slack_id,
                blocks=prompt["blocks"]
            )
            
            # Create submission tracker entry
            tracker = SubmissionTracker(
                contractor_id=contractor.id,
                date=datetime.utcnow().date(),
                submitted=False
            )
            db.session.add(tracker)
        
        db.session.commit()
    except Exception as e:
        logger.error(f"Error sending EOD prompts: {e}")

@scheduler.task('cron', id='send_reminders', hour=17, minute=30)
def send_reminders():
    """Send reminders to contractors who haven't submitted their EOD"""
    try:
        today = datetime.utcnow().date()
        trackers = SubmissionTracker.query.filter_by(
            date=today,
            submitted=False
        ).all()
        
        for tracker in trackers:
            contractor = Contractor.query.get(tracker.contractor_id)
            if contractor:
                slack_client.chat_postMessage(
                    channel=contractor.slack_id,
                    text="Reminder: Please submit your EOD report for today!"
                )
                
                tracker.last_reminder = datetime.utcnow()
                db.session.add(tracker)
        
        db.session.commit()
    except Exception as e:
        logger.error(f"Error sending reminders: {e}")

@scheduler.task('cron', id='escalate_missing_reports', hour=18)
def escalate_missing_reports():
    """Escalate contractors who consistently miss EOD reports"""
    try:
        cutoff_date = datetime.utcnow().date() - timedelta(days=3)
        missing_reports = db.session.query(SubmissionTracker)\
            .filter(
                SubmissionTracker.date >= cutoff_date,
                SubmissionTracker.submitted == False
            )\
            .group_by(SubmissionTracker.contractor_id)\
            .having(db.func.count() >= 3)\
            .all()
        
        if missing_reports:
            # Send to management channel
            message = "The following contractors have missed 3+ EOD reports:\n"
            for report in missing_reports:
                contractor = Contractor.query.get(report.contractor_id)
                message += f"• {contractor.name}\n"
            
            slack_client.chat_postMessage(
                channel="#management",  # Replace with actual channel
                text=message
            )
    except Exception as e:
        logger.error(f"Error escalating missing reports: {e}")
