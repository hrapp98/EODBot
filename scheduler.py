from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta, date
import logging
from models import EODReport, SubmissionTracker
from sheets_client import SheetsClient
from config import Config
from zoneinfo import ZoneInfo
import traceback
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

logger = logging.getLogger(__name__)

# Single user to receive all notifications
TARGET_USER_ID = "U083K838X8V"  # Harlan's user ID

# Management channel for reports
MANAGEMENT_CHANNEL = "C08MD128A80"  # Private channel for management reports

# Define holidays
HOLIDAYS = {
    date(2024, 1, 1): "New Year's Day",
    date(2024, 4, 17): "Maundy Thursday",
    date(2024, 4, 18): "Good Friday",
    date(2024, 5, 1): "Labor Day",
    date(2024, 6, 12): "Independence Day",
    date(2024, 8, 25): "National Heroes Day",
    date(2024, 12, 25): "Christmas Day",
    date(2024, 12, 30): "Rizal Day"
}

def setup_scheduler(app):
    """Initialize and start the scheduler"""
    scheduler = BackgroundScheduler()
    
    # Calculate a time 30 seconds from now for initial run
    now = datetime.now()
    initial_run_time = now + timedelta(seconds=30)
    
    # Send EOD prompts at 4:00 PM ET
    scheduler.add_job(
        send_eod_prompts,
        CronTrigger(hour=16, minute=0, timezone="America/New_York"),
        args=[app],
        id='eod_prompts'
    )
    
    # Send reminders at 6:00 PM ET
    scheduler.add_job(
        send_reminders,
        CronTrigger(hour=18, minute=0, timezone="America/New_York"),
        args=[app],
        id='reminders'
    )
    
    # Send final reminders at 7:30 PM ET
    scheduler.add_job(
        send_final_reminders,
        CronTrigger(hour=19, minute=30, timezone="America/New_York"),
        args=[app],
        id='last_call_reminders'
    )
    
    # Send management report at 12:01 AM ET (after 11:59 PM cutoff)
    scheduler.add_job(
        send_daily_non_submission_report,
        CronTrigger(hour=0, minute=1, timezone="America/New_York"),
        args=[app],
        id='daily_non_submission_report'
    )
    
    # Weekly Summary every Friday at 5:00 PM ET
    scheduler.add_job(
        generate_weekly_summary,
        CronTrigger(day_of_week='fri', hour=17, minute=0, timezone="America/New_York"),
        args=[app],
        id='weekly_summary'
    )
    
    # Update Google Sheets tracker daily at 12:05 AM ET (after 11:59 PM cutoff)
    scheduler.add_job(
        update_sheets_tracker,
        CronTrigger(hour=0, minute=5, timezone="America/New_York"),
        args=[app],
        id='update_sheets_tracker'
    )
    
    # Start the scheduler
    scheduler.start()
    logger.info("Scheduler started")
    
    return scheduler

def send_eod_prompts(app):
    """Send EOD prompts to users"""
    with app.app_context():
        try:
            from app import slack_bot, firebase_client
            
            # Check if Firebase client is initialized
            if not firebase_client:
                logger.error("Firebase client not initialized. Cannot send EOD prompts.")
                return
            
            # Skip weekends
            now = datetime.now(ZoneInfo("America/New_York"))
            if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
                logger.info("Skipping EOD prompts for weekend")
                return
            
            # Define internal team user IDs to exclude
            INTERNAL_TEAM_IDS = [
                "U083K838X8V",  # Harlan
                "U0890AG4ZEU",
                "U0837HZE98X",
                "U08CSFHTJ2X",
                "USLACKBOT"     # Exclude Slackbot
            ]
            
            # Get date range for today
            today = now.date()
            start = datetime.combine(today, datetime.min.time()).replace(tzinfo=ZoneInfo("America/New_York"))
            end = datetime.combine(today, datetime.max.time()).replace(tzinfo=ZoneInfo("America/New_York"))
            
            # Convert to UTC for Firebase query
            start_utc = start.astimezone(ZoneInfo("UTC"))
            end_utc = end.astimezone(ZoneInfo("UTC"))
            
            # Get users who have submitted today using the date field
            submitted_users = set()
            try:
                today_date_str = today.strftime('%Y-%m-%d')
                # Query for today's submissions using date field
                today_docs = firebase_client.db.collection('eod_reports').where('date', '==', today_date_str).stream()
                
                # Process each document
                for doc in today_docs:
                    doc_data = doc.to_dict()
                    user_id = doc_data.get('user_id')
                    if user_id:
                        submitted_users.add(user_id)
                
                logger.info(f"Found {len(submitted_users)} users who have already submitted today")
            except Exception as e:
                logger.error(f"Error getting submitted users: {str(e)}")
            
            # Get all users from Slack
            all_users = []
            try:
                # Get all users from Slack
                response = slack_bot.client.users_list()
                all_users = response["members"]
                logger.info(f"Retrieved {len(all_users)} users from Slack")
            except Exception as e:
                logger.error(f"Error getting users from Slack: {str(e)}")
                return
            
            # Create EOD prompt message
            message = ("🔔 *Daily EOD Reminder*\n"
                      "Please submit your End-of-Day report using the `/eod` command.")
            
            # Send to all active users except internal team, bots, deactivated accounts, and those who already submitted
            sent_count = 0
            for user in all_users:
                user_id = user.get("id")
                
                # Skip if user is in internal team
                if user_id in INTERNAL_TEAM_IDS:
                    logger.info(f"Skipping internal team member: {user_id}")
                    continue
                
                # Skip if user is a bot
                if user.get("is_bot", False):
                    logger.info(f"Skipping bot user: {user_id}")
                    continue
                
                # Skip if user is deactivated
                if user.get("deleted", False):
                    logger.info(f"Skipping deactivated user: {user_id}")
                    continue
                
                # Skip if user has already submitted
                if user_id in submitted_users:
                    logger.info(f"Skipping user who already submitted: {user_id}")
                    continue
                
                # Send message to user
                slack_bot.send_message(user_id, message)
                sent_count += 1
                logger.info(f"Sent EOD prompt to user {user_id}")
            
            logger.info(f"Sent EOD prompts to {sent_count} users")
                
        except Exception as e:
            logger.error(f"Error sending EOD prompts: {str(e)}")
            logger.error(traceback.format_exc())

def send_reminders(app):
    """Send reminders to users who haven't submitted reports"""
    with app.app_context():
        try:
            from app import slack_bot, firebase_client
            
            # Check if Firebase client is initialized
            if not firebase_client:
                logger.error("Firebase client not initialized. Cannot send reminders.")
                return
            
            # Skip weekends
            now = datetime.now(ZoneInfo("America/New_York"))
            if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
                logger.info("Skipping reminders for weekend")
                return
            
            # Define internal team user IDs to exclude
            INTERNAL_TEAM_IDS = [
                "U083K838X8V",  # Harlan
                "U0890AG4ZEU",
                "U0837HZE98X",
                "U08CSFHTJ2X",
                "USLACKBOT"     # Exclude Slackbot
            ]
            
            # Get date range for today
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Get all users from Slack
            all_users = []
            try:
                # Get all users from Slack
                response = slack_bot.client.users_list()
                all_users = response["members"]
                logger.info(f"Retrieved {len(all_users)} users from Slack")
            except Exception as e:
                logger.error(f"Error getting users from Slack: {str(e)}")
                return
            
            # Get users who have submitted today
            submitted_users = set()
            try:
                # Convert to UTC for Firebase query
                start_utc = start.astimezone(ZoneInfo("UTC"))
                end_utc = end.astimezone(ZoneInfo("UTC"))
                
                # Query for today's submissions
                today_docs = firebase_client.db.collection('eod_reports').where('timestamp', '>=', start_utc).where('timestamp', '<=', end_utc).stream()
                
                # Process each document
                for doc in today_docs:
                    doc_data = doc.to_dict()
                    user_id = doc_data.get('user_id')
                    if user_id:
                        submitted_users.add(user_id)
                
                logger.info(f"Found {len(submitted_users)} users who have submitted today")
            except Exception as e:
                logger.error(f"Error getting submitted users: {str(e)}")
            
            # Create reminder message
            message = "⏰ *Reminder*: Please submit your EOD report for today using the `/eod` command."
            
            # Send to all active users who haven't submitted yet
            sent_count = 0
            for user in all_users:
                user_id = user.get("id")
                
                # Skip if user is in internal team
                if user_id in INTERNAL_TEAM_IDS:
                    logger.info(f"Skipping internal team member: {user_id}")
                    continue
                
                # Skip if user is a bot
                if user.get("is_bot", False):
                    logger.info(f"Skipping bot user: {user_id}")
                    continue
                
                # Skip if user is deactivated
                if user.get("deleted", False):
                    logger.info(f"Skipping deactivated user: {user_id}")
                    continue
                
                # Skip if user has already submitted
                if user_id in submitted_users:
                    logger.info(f"Skipping user who already submitted: {user_id}")
                    continue
                
                # Send message to user
                slack_bot.send_message(user_id, message)
                sent_count += 1
                logger.info(f"Sent reminder to user {user_id}")
            
            logger.info(f"Sent reminders to {sent_count} users")
                
        except Exception as e:
            logger.error(f"Error sending reminders: {str(e)}")
            logger.error(traceback.format_exc())

def send_final_reminders(app):
    """Send final reminders to users who haven't submitted reports"""
    with app.app_context():
        try:
            from app import slack_bot, firebase_client
            
            # Check if Firebase client is initialized
            if not firebase_client:
                logger.error("Firebase client not initialized. Cannot send final reminders.")
                return
            
            # Skip weekends
            now = datetime.now(ZoneInfo("America/New_York"))
            if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
                logger.info("Skipping final reminders for weekend")
                return
            
            # Define internal team user IDs to exclude
            INTERNAL_TEAM_IDS = [
                "U083K838X8V",  # Harlan
                "U0890AG4ZEU",
                "U0837HZE98X",
                "U08CSFHTJ2X",
                "USLACKBOT"     # Exclude Slackbot
            ]
            
            # Get date range for today
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Get all users from Slack
            all_users = []
            try:
                # Get all users from Slack
                response = slack_bot.client.users_list()
                all_users = response["members"]
                logger.info(f"Retrieved {len(all_users)} users from Slack")
            except Exception as e:
                logger.error(f"Error getting users from Slack: {str(e)}")
                return
            
            # Get users who have submitted today
            submitted_users = set()
            try:
                # Convert to UTC for Firebase query
                start_utc = start.astimezone(ZoneInfo("UTC"))
                end_utc = end.astimezone(ZoneInfo("UTC"))
                
                # Query for today's submissions
                today_docs = firebase_client.db.collection('eod_reports').where('timestamp', '>=', start_utc).where('timestamp', '<=', end_utc).stream()
                
                # Process each document
                for doc in today_docs:
                    doc_data = doc.to_dict()
                    user_id = doc_data.get('user_id')
                    if user_id:
                        submitted_users.add(user_id)
                
                logger.info(f"Found {len(submitted_users)} users who have submitted today")
            except Exception as e:
                logger.error(f"Error getting submitted users: {str(e)}")
            
            # Create final reminder message
            message = ("🚨 *Last Call*\nYou haven't submitted your EOD report for today. "
                      "Please submit it in the next 30 minutes before the daily report is sent to management.")
            
            # Send to all active users who haven't submitted yet
            sent_count = 0
            for user in all_users:
                user_id = user.get("id")
                
                # Skip if user is in internal team
                if user_id in INTERNAL_TEAM_IDS:
                    logger.info(f"Skipping internal team member: {user_id}")
                    continue
                
                # Skip if user is a bot
                if user.get("is_bot", False):
                    logger.info(f"Skipping bot user: {user_id}")
                    continue
                
                # Skip if user is deactivated
                if user.get("deleted", False):
                    logger.info(f"Skipping deactivated user: {user_id}")
                    continue
                
                # Skip if user has already submitted
                if user_id in submitted_users:
                    logger.info(f"Skipping user who already submitted: {user_id}")
                    continue
                
                # Send message to user
                slack_bot.send_message(user_id, message)
                sent_count += 1
                logger.info(f"Sent final reminder to user {user_id}")
            
            logger.info(f"Sent final reminders to {sent_count} users")
                
        except Exception as e:
            logger.error(f"Error sending final reminders: {str(e)}")
            logger.error(traceback.format_exc())

def send_daily_non_submission_report(app):
    """Send daily report of non-submissions to management"""
    with app.app_context():
        try:
            from app import slack_bot, firebase_client
            
            # Check if Firebase client is initialized
            if not firebase_client:
                logger.error("Firebase client not initialized. Cannot send non-submission report.")
                return
            
            # Skip weekends
            now = datetime.now(ZoneInfo("America/New_York"))
            if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
                logger.info("Skipping non-submission report for weekend")
                return
            
            # Get today's date
            today = now.date()
            logger.info(f"Generating non-submission report for date: {today}")
            
            # Define internal team user IDs to exclude
            INTERNAL_TEAM_IDS = [
                "U083K838X8V",  # Harlan
                "U0890AG4ZEU",
                "U0837HZE98X",
                "U08CSFHTJ2X",
                "USLACKBOT"     # Exclude Slackbot
            ]
            logger.info(f"Will exclude internal team members and Slackbot: {INTERNAL_TEAM_IDS}")
            

            
            # Get all active users from the users collection who have submitted at least one EOD report
            all_users = set()
            users_docs = list(firebase_client.db.collection('users').where('status', '==', 'active').stream())
            logger.info(f"Found {len(users_docs)} active users in the database")
            
            # Get all users who have ever submitted an EOD report
            eod_submitters = set()
            eod_docs = firebase_client.db.collection('eod_reports').select(['user_id']).stream()
            for doc in eod_docs:
                data = doc.to_dict()
                user_id = data.get('user_id')
                if user_id:
                    eod_submitters.add(user_id)
            
            logger.info(f"Found {len(eod_submitters)} users who have submitted EOD reports")
            
            for doc in users_docs:
                user_data = doc.to_dict()
                user_id = user_data.get('slack_id')
                if user_id and user_id not in INTERNAL_TEAM_IDS and user_id in eod_submitters:  # Only include users who have submitted EODs
                    all_users.add(user_id)
            
            logger.info(f"Found {len(all_users)} active users who should submit EOD reports (excluding internal team and Slackbot)")
            
            # Get user names from Slack and filter out bots and deactivated accounts
            user_names = {}
            valid_users = set()
            
            for user_id in all_users:
                try:
                    # Skip Slackbot explicitly
                    if user_id == "USLACKBOT":
                        logger.info(f"Skipping Slackbot user: {user_id}")
                        continue
                    

                        
                    user_info = slack_bot.client.users_info(user=user_id)
                    
                    # Skip if user is a bot
                    if user_info.get('user', {}).get('is_bot', False):
                        logger.info(f"Skipping bot user: {user_id}")
                        continue
                    
                    # Skip if user is deactivated
                    if user_info.get('user', {}).get('deleted', False):
                        logger.info(f"Skipping deactivated user: {user_id}")
                        continue
                    
                    # Skip if user is in internal team
                    if user_id in INTERNAL_TEAM_IDS:
                        logger.info(f"Skipping internal team member: {user_id}")
                        continue
                    
                    user_name = user_info['user']['real_name'] if user_info else f"Unknown ({user_id})"
                    user_names[user_id] = user_name
                    valid_users.add(user_id)
                    logger.info(f"Valid user: {user_name} (ID: {user_id})")
                except Exception as e:
                    logger.error(f"Error getting user info: {str(e)}")
                    # Skip users we can't get info for - they might be invalid
            
            logger.info(f"Found {len(valid_users)} valid active users (non-bot, non-deactivated, non-internal, non-Slackbot)")
            
            # Use the date field instead of timestamp ranges for more reliable querying
            today_date_str = today.strftime('%Y-%m-%d')
            logger.info(f"Looking for submissions with date field: {today_date_str}")
            
            # Initialize empty set for submitted users
            submitted_today = set()
            
            # Query specifically for today's submissions using the date field
            today_docs = firebase_client.db.collection('eod_reports').where('date', '==', today_date_str).stream()
            
            # Process each document from today's query
            logger.info(f"=== PROCESSING TODAY'S SUBMISSIONS FOR DATE {today_date_str} ===")
            for doc in today_docs:
                doc_data = doc.to_dict()
                doc_id = doc.id
                user_id = doc_data.get('user_id', 'No user ID')
                timestamp = doc_data.get('timestamp')
                date_field = doc_data.get('date')
                
                if not timestamp:
                    logger.warning(f"Document {doc_id} has no timestamp, skipping")
                    continue
                
                user_name = user_names.get(user_id, f"Unknown ({user_id})")
                logger.info(f"✅ FOUND SUBMISSION: {user_name} (ID: {user_id})")
                logger.info(f"   - Timestamp: {timestamp}")
                logger.info(f"   - Date field: {date_field}")
                logger.info(f"   - Document ID: {doc_id}")
                submitted_today.add(user_id)
            
            logger.info(f"Found {len(submitted_today)} users who submitted today")
            logger.info(f"Users who submitted: {list(submitted_today)}")
            
            # Calculate missing users
            missing_users = [user_id for user_id in valid_users if user_id not in submitted_today]
            logger.info(f"Missing users count: {len(missing_users)} out of {len(valid_users)} total valid users")
            logger.info(f"Valid users list: {list(valid_users)}")
            logger.info(f"Missing users list: {missing_users}")
            
            # Get past submissions to calculate consecutive missed days
            past_submissions = {}
            
            # Get submissions from the past 30 days using date field
            thirty_days_ago = today - timedelta(days=30)
            logger.info(f"Getting past submissions from {thirty_days_ago} to {today}")
            
            # Get all submissions and filter by date field
            all_past_docs = firebase_client.db.collection('eod_reports').stream()
            
            for doc in all_past_docs:
                doc_data = doc.to_dict()
                user_id = doc_data.get('user_id')
                date_str = doc_data.get('date')
                
                if not user_id or not date_str:
                    continue
                
                # Skip internal team
                if user_id in INTERNAL_TEAM_IDS:
                    continue
                
                try:
                    # Parse the date string
                    submission_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    
                    # Only include dates within our range
                    if thirty_days_ago <= submission_date <= today:
                        if user_id not in past_submissions:
                            past_submissions[user_id] = set()
                        
                        past_submissions[user_id].add(submission_date)
                except ValueError:
                    logger.warning(f"Invalid date format in document {doc.id}: {date_str}")
                    continue
            
            # Now calculate consecutive missed days for each missing user
            consecutive_missed_days = {}
            for user_id in missing_users:
                # Start from yesterday and go backwards
                check_date = today - timedelta(days=1)
                consecutive_days = 1  # Today is already missed
                
                while True:
                    # Skip weekends and holidays
                    if check_date.weekday() >= 5 or check_date in HOLIDAYS:
                        check_date = check_date - timedelta(days=1)
                        continue
                    
                    # Check if user submitted on this date
                    user_submissions = past_submissions.get(user_id, set())
                    if check_date in user_submissions:
                        # Found a submission, stop counting
                        break
                    else:
                        # No submission found, increment counter
                        consecutive_days += 1
                        check_date = check_date - timedelta(days=1)
                        
                        # Limit how far back we check
                        if consecutive_days >= 30 or check_date < thirty_days_ago:
                            break
                
                consecutive_missed_days[user_id] = consecutive_days
            
            # Sort missing users by name for the report
            missing_users_with_names = [(user_id, user_names.get(user_id, "Unknown")) for user_id in missing_users]
            missing_users_with_names.sort(key=lambda x: x[1])  # Sort by name
            
            # Create management message
            mgmt_message = (
                "📊 *Daily EOD Submission Report*\n"
                f"📅 *Date:* {today.strftime('%A, %B %d, %Y')}\n\n"
            )
            
            if missing_users:
                mgmt_message += "⚠️ *Missing Submissions:*\n"
                
                # Add missing users to report (alphabetically by name)
                for user_id, user_name in missing_users_with_names:
                    consecutive_days = consecutive_missed_days.get(user_id, 1)
                    streak_text = "day" if consecutive_days == 1 else "days"
                    mgmt_message += f"• *{user_name}* (<@{user_id}>)\n"
                    mgmt_message += f"   ↳ _Missed {consecutive_days} consecutive working {streak_text}_\n"
                    logger.info(f"Adding to report: {user_name} (ID: {user_id}) - {consecutive_days} consecutive missed days")
                
                # Add summary count
                mgmt_message += f"\n_Total: {len(missing_users)} missing out of {len(valid_users)} expected submissions_"
            else:
                mgmt_message += "✅ *All team members have submitted their EOD reports today!*"
            
            # Log the final message
            logger.info(f"Final management message:\n{mgmt_message}")
            
            # Send to management channel
            slack_bot.send_message(MANAGEMENT_CHANNEL, mgmt_message)
            logger.info(f"Sent management report to channel {MANAGEMENT_CHANNEL}")
                
        except Exception as e:
            logger.error(f"Error sending non-submission report: {str(e)}")
            logger.error(traceback.format_exc())

def generate_weekly_summary(app):
    """Generate and send weekly summary report"""
    with app.app_context():
        try:
            from app import slack_bot
            
            # Only run on Fridays
            now = datetime.now(ZoneInfo("America/New_York"))
            if now.weekday() != 4:  # Friday = 4
                logger.info("Skipping weekly summary - not Friday")
                return
            
            # Generate weekly summary message
            message = "*Weekly Progress Summary*\n"
            message += f"Week ending: {now.strftime('%Y-%m-%d')}\n\n"
            message += "This is a placeholder for the weekly summary report.\n"
            message += "In the future, this will contain a summary of all EOD reports for the week."
            
            # Send to target user only
            slack_bot.send_message(TARGET_USER_ID, message)
            logger.info(f"Sent weekly summary to user {TARGET_USER_ID}")
                
        except Exception as e:
            logger.error(f"Error generating weekly summary: {str(e)}")
            logger.error(traceback.format_exc())

def update_sheets_tracker(app):
    """Update the submission tracker sheet with latest data"""
    with app.app_context():
        try:
            logger.info("Updating tracker sheet with latest submission data")
            sheets_client = SheetsClient()
            sheets_client.update_tracker()
            logger.info("Tracker sheet update complete")
        except Exception as e:
            logger.error(f"Error updating tracker sheet: {str(e)}")
            logger.error(traceback.format_exc())

def update_tracker_with_test_data(app):
    """Send test notifications about missed submissions for April 3rd"""
    with app.app_context():
        try:
            logger.info("Starting test notification process for April 3rd")
            
            # Send notification about missed submissions
            logger.info("Sending test notification about missed submissions")
            try:
                from app import slack_bot, firebase_client
                
                # Get today's actual submissions
                today = datetime.now(ZoneInfo("America/New_York")).date()
                logger.info(f"TODAY'S DATE: {today} (America/New_York timezone)")
                
                # CRITICAL: Get all active users first
                all_users_data = firebase_client.get_all_users()
                logger.info(f"TOTAL USERS IN SYSTEM: {len(all_users_data)}")
                
                # Filter to only active users and extract slack_ids
                all_users = set()
                for user in all_users_data:
                    if user.get('status') == 'active' and user.get('slack_id'):
                        all_users.add(user.get('slack_id'))
                
                logger.info(f"ACTIVE USERS: {len(all_users)}")
                
                # Create a dictionary to store user names
                user_names = {}
                for user_id in all_users:
                    try:
                        user_info = slack_bot.client.users_info(user=user_id)
                        user_name = user_info['user']['real_name'] if user_info else f"Unknown ({user_id})"
                        user_names[user_id] = user_name
                        logger.info(f"USER: {user_name} (ID: {user_id})")
                    except Exception as e:
                        logger.error(f"Error getting user info: {str(e)}")
                        user_names[user_id] = f"Unknown ({user_id})"
                
                # CRITICAL: Get today's submissions with explicit date filtering
                logger.info("=== GETTING TODAY'S SUBMISSIONS WITH EXPLICIT DATE FILTERING ===")
                
                # Define today's date range in UTC (since Firebase stores in UTC)
                today_start_ny = datetime.combine(today, datetime.min.time()).replace(tzinfo=ZoneInfo("America/New_York"))
                today_end_ny = datetime.combine(today, datetime.max.time()).replace(tzinfo=ZoneInfo("America/New_York"))
                
                # Convert to UTC for Firebase query
                today_start_utc = today_start_ny.astimezone(ZoneInfo("UTC"))
                today_end_utc = today_end_ny.astimezone(ZoneInfo("UTC"))
                
                logger.info(f"FILTERING FOR SUBMISSIONS BETWEEN {today_start_utc} AND {today_end_utc} (UTC)")
                
                # Initialize empty set for submitted users
                submitted_today = set()
                
                # CRITICAL: Query specifically for today's submissions in UTC
                today_docs = firebase_client.db.collection('eod_reports').where('timestamp', '>=', today_start_utc).where('timestamp', '<=', today_end_utc).stream()
                
                # Process each document from today's query
                logger.info("=== PROCESSING TODAY'S SUBMISSIONS ===")
                for doc in today_docs:
                    doc_data = doc.to_dict()
                    doc_id = doc.id
                    user_id = doc_data.get('user_id', 'No user ID')
                    timestamp = doc_data.get('timestamp')
                    
                    if not timestamp:
                        logger.warning(f"DOCUMENT {doc_id} HAS NO TIMESTAMP, SKIPPING")
                        continue
                    
                    user_name = user_names.get(user_id, f"Unknown ({user_id})")
                    logger.info(f"TODAY'S SUBMISSION: {user_name} (ID: {user_id}) at {timestamp}")
                    submitted_today.add(user_id)
                
                logger.info(f"FOUND {len(submitted_today)} USERS WHO SUBMITTED TODAY")
                
                # CRITICAL: Explicitly log who submitted and who didn't
                logger.info("=== SUBMISSION STATUS FOR ALL USERS ===")
                for user_id, user_name in user_names.items():
                    if user_id in submitted_today:
                        logger.info(f"✅ SUBMITTED: {user_name} (ID: {user_id})")
                    else:
                        logger.info(f"❌ NOT SUBMITTED: {user_name} (ID: {user_id})")
                logger.info("=== END SUBMISSION STATUS ===")
                
                # Calculate missing users
                missing_users = [user_id for user_id in all_users if user_id not in submitted_today]
                logger.info(f"MISSING USERS COUNT: {len(missing_users)} OUT OF {len(all_users)} TOTAL USERS")
                
                # Create management message
                mgmt_message = (f"*Daily EOD Submission Report*\n"
                               f"Date: {today.strftime('%Y-%m-%d')}\n\n")
                
                if missing_users:
                    mgmt_message += "*Missing Submissions:*\n"
                    
                    for user_id in missing_users:
                        user_name = user_names.get(user_id, "Unknown")
                        mgmt_message += f"• {user_name} (<@{user_id}>)\n"
                        logger.info(f"ADDING TO REPORT: {user_name} (ID: {user_id})")
                else:
                    mgmt_message += "✅ All team members have submitted their EOD reports today!"
                
                # Log the final message
                logger.info(f"FINAL MANAGEMENT MESSAGE:\n{mgmt_message}")
                
                # Send to target user
                slack_bot.send_message(TARGET_USER_ID, mgmt_message)
                logger.info(f"SENT MANAGEMENT REPORT TO USER {TARGET_USER_ID}")
                
                # Also send to management users if defined
                MANAGEMENT_USERS = [TARGET_USER_ID]  # Define management users
                for mgmt_user_id in MANAGEMENT_USERS:
                    if mgmt_user_id != TARGET_USER_ID:  # Avoid duplicate to test user
                        slack_bot.send_message(mgmt_user_id, mgmt_message)
                
            except Exception as e:
                logger.error(f"ERROR SENDING TEST NOTIFICATIONS: {str(e)}")
                logger.error(traceback.format_exc())
            
            logger.info("Test notification process completed successfully")
        except Exception as e:
            logger.error(f"Error in test notification process: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
