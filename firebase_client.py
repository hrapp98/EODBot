import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import json
import logging
from config import Config
from zoneinfo import ZoneInfo
import traceback

logger = logging.getLogger(__name__)

class FirebaseClient:
    def __init__(self):
        """Initialize Firebase client with proper error handling"""
        self.db = None
        try:
            if not firebase_admin._apps:
                if not Config.firebase_config_valid():
                    logger.error("Missing required Firebase configuration")
                    return
                
                logger.info("Initializing Firebase client...")
                
                # Create service account info from environment variables
                service_account_info = {
                    "type": "service_account",
                    "project_id": Config.FIREBASE_PROJECT_ID,
                    "private_key_id": Config.FIREBASE_API_KEY,  # This should be a separate secret, but API key will work for now
                    "private_key": Config.FIREBASE_PRIVATE_KEY,
                    "client_email": Config.FIREBASE_CLIENT_EMAIL,
                    "client_id": "",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{Config.FIREBASE_CLIENT_EMAIL.replace('@', '%40')}"
                }
                
                # Ensure private key is properly formatted
                if service_account_info['private_key']:
                    service_account_info['private_key'] = service_account_info['private_key'].replace('\\n', '\n')
                
                # Verify required fields
                if not service_account_info['private_key']:
                    logger.error("Firebase private key is missing")
                    return
                    
                logger.debug("Firebase service account info validation:")
                logger.debug(f"- Project ID: {Config.FIREBASE_PROJECT_ID}")
                logger.debug(f"- Client Email: {Config.FIREBASE_CLIENT_EMAIL}")
                logger.debug(f"- Private key format: {service_account_info['private_key'].startswith('-----BEGIN PRIVATE KEY-----')}")
                
                # Initialize Firebase with credentials
                try:
                    logger.info("Attempting to initialize Firebase with credentials...")
                    cred = credentials.Certificate(service_account_info)
                    firebase_admin.initialize_app(cred)
                    logger.info("Firebase app initialized successfully")
                except ValueError as ve:
                    logger.error(f"Invalid credential format: {str(ve)}")
                    return
                except Exception as e:
                    logger.error(f"Failed to initialize Firebase app: {str(e)}")
                    return
            
            # Initialize Firestore client
            try:
                self.db = firestore.client()
                # Verify connection by attempting a simple operation
                self.db.collection('test').limit(1).get()
                logger.info("Firestore client initialized and verified successfully")
            except Exception as e:
                logger.error(f"Failed to initialize or verify Firestore client: {str(e)}")
                self.db = None
                
        except Exception as e:
            logger.error(f"Unexpected error in Firebase initialization: {str(e)}")
            self.db = None

    def save_eod_report(self, user_id, report_data):
        """Save EOD report to Firestore"""
        try:
            # Get user info from Slack
            from slack_client import SlackClient
            slack_client = SlackClient(Config.SLACK_BOT_OAUTH_TOKEN)
            user_info = slack_client.get_user_info(user_id)
            
            if user_info:
                report_data['user_name'] = user_info.get('real_name', 'Unknown')
                report_data['user_email'] = user_info.get('profile', {}).get('email', 'Unknown')
            else:
                report_data['user_name'] = 'Unknown'
                report_data['user_email'] = 'Unknown'
            
            # Add timestamp and user_id
            report_data['timestamp'] = datetime.now(tz=ZoneInfo("UTC"))
            report_data['user_id'] = user_id
            report_data['date'] = report_data['timestamp'].strftime('%Y-%m-%d')
            
            # Save to Firestore
            doc_ref = self.db.collection('eod_reports').document()
            doc_ref.set(report_data)
            
            logger.info(f"Successfully saved EOD report for user {user_id} ({report_data['user_name']})")
            return doc_ref.id
            
        except Exception as e:
            logger.error(f"Error saving EOD report: {str(e)}")
            raise

    def get_user_reports(self, user_id, date=None):
        """Get EOD reports for a specific user"""
        if not self.db:
            logger.error("Firebase client not initialized")
            return []
            
        try:
            query = self.db.collection('eod_reports').where('user_id', '==', user_id)
            if date:
                query = query.where('timestamp', '>=', date)
            return [doc.to_dict() for doc in query.stream()]
        except Exception as e:
            logger.error(f"Error getting user reports: {str(e)}")
            return []

    def get_missing_reports(self, date):
        """Get list of users who haven't submitted reports for a given date"""
        if not self.db:
            logger.error("Firebase client not initialized")
            return set()
            
        try:
            query = self.db.collection('eod_reports').where('timestamp', '>=', date)
            submitted_users = set(doc.get('user_id') for doc in query.stream())
            return submitted_users
        except Exception as e:
            logger.error(f"Error getting missing reports: {str(e)}")
            return set()

    def save_tracker(self, tracker_data):
        """Save submission tracker to Firebase"""
        if not self.db:
            logger.error("Firebase client not initialized")
            return None
            
        try:
            doc_ref = self.db.collection('submission_trackers').document()
            doc_ref.set(tracker_data)
            return doc_ref.id
        except Exception as e:
            logger.error(f"Error saving tracker: {str(e)}")
            return None

    def get_tracker(self, user_id, date):
        """Get tracker for a specific user and date"""
        if not self.db:
            logger.error("Firebase client not initialized")
            return None
            
        try:
            query = self.db.collection('submission_trackers')\
                .where('user_id', '==', user_id)\
                .where('date', '==', date)
            docs = list(query.stream())
            return docs[0].to_dict() if docs else None
        except Exception as e:
            logger.error(f"Error getting tracker: {str(e)}")
            return None

    def get_user_report_for_date(self, user_id, date):
        """Get user's report for a specific date in EST timezone"""
        if not self.db:
            logger.error("Firebase client not initialized")
            return None
        
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            
            # Convert date to start and end of day in EST
            start_of_day = datetime.combine(date, datetime.min.time())
            start_of_day = start_of_day.replace(tzinfo=ZoneInfo("America/New_York"))
            
            end_of_day = datetime.combine(date, datetime.max.time())
            end_of_day = end_of_day.replace(tzinfo=ZoneInfo("America/New_York"))
            
            logger.debug(f"Checking for reports between {start_of_day.isoformat()} and {end_of_day.isoformat()}")
            logger.debug(f"Querying for user_id: {user_id}")
            
            # Query for reports within the day
            reports_ref = self.db.collection('eod_reports')
            query = reports_ref.where('user_id', '==', user_id)
            
            # Get all documents and filter in Python (temporary workaround)
            docs = query.stream()
            matching_reports = []
            
            for doc in docs:
                data = doc.to_dict()
                timestamp = data.get('timestamp')
                if isinstance(timestamp, datetime):
                    if start_of_day <= timestamp <= end_of_day:
                        data['id'] = doc.id
                        matching_reports.append(data)
                        logger.debug(f"Found matching report: {data}")
            
            if matching_reports:
                return matching_reports[0]
            
            logger.debug("No existing report found")
            return None
            
        except Exception as e:
            logger.error(f"Error getting user report: {str(e)}")
            return None

    def update_eod_report(self, report_id, report_data):
        """Update existing EOD report in Firebase"""
        if not self.db:
            logger.error("Firebase client not initialized")
            raise RuntimeError("Firebase client not initialized")
        
        try:
            # Use EST timezone for consistency
            now = datetime.now(ZoneInfo("America/New_York"))
            report_data['timestamp'] = now  # Update timestamp
            report_data['date'] = now.date().isoformat()  # Update date
            
            # Get user info from Slack if not already present
            if 'user_name' not in report_data or 'user_email' not in report_data:
                try:
                    from slack_client import SlackClient
                    slack_client = SlackClient(Config.SLACK_BOT_OAUTH_TOKEN)
                    user_info = slack_client.get_user_info(report_data['user_id'])
                    if user_info:
                        report_data['user_name'] = user_info.get('real_name', 'Unknown')
                        report_data['user_email'] = user_info.get('profile', {}).get('email', 'Unknown')
                except Exception as e:
                    logger.error(f"Error getting Slack user info: {str(e)}")
                    report_data['user_name'] = 'Unknown'
                    report_data['user_email'] = 'Unknown'
            
            doc_ref = self.db.collection('eod_reports').document(report_id)
            doc_ref.update(report_data)
            logger.info(f"Successfully updated EOD report {report_id}")
            return report_id
        except Exception as e:
            logger.error(f"Error updating EOD report: {str(e)}")
            raise

    def save_reminder(self, user_id, reminder_type='daily'):
        """Save reminder record to Firestore"""
        try:
            now = datetime.now(ZoneInfo("UTC"))
            reminder_data = {
                'user_id': user_id,
                'timestamp': now,
                'type': reminder_type,
                'date': now.strftime('%Y-%m-%d')
            }
            
            # Save to Firestore
            doc_ref = self.db.collection('reminders').document()
            doc_ref.set(reminder_data)
            logger.info(f"Saved reminder for user {user_id}")
            return doc_ref.id
            
        except Exception as e:
            logger.error(f"Error saving reminder: {str(e)}")
            return None

    def get_missed_submissions(self, start_date, end_date):
        """Get users who missed submissions in date range"""
        try:
            # Get all active users
            active_users = set(self._get_active_users())
            logger.debug(f"Active users: {active_users}")
            
            # Get all submissions in date range
            submissions = self.db.collection('eod_reports')\
                .where('timestamp', '>=', start_date)\
                .where('timestamp', '<=', end_date)\
                .stream()
            
            # Track submissions by user and date
            submitted = {}
            for doc in submissions:
                data = doc.to_dict()
                user_id = data.get('user_id')
                timestamp = data.get('timestamp')
                if timestamp:  # Make sure timestamp exists
                    date = timestamp.date()
                    logger.debug(f"Found submission from {user_id} for date {date}")
                    
                    if user_id not in submitted:
                        submitted[user_id] = set()
                    submitted[user_id].add(date)
            
            logger.debug(f"Submitted reports: {submitted}")
            
            # Find users with missing submissions
            missing = {}
            current = start_date.date()
            while current <= end_date.date():
                for user_id in active_users:
                    if user_id not in submitted or current not in submitted[user_id]:
                        if user_id not in missing:
                            missing[user_id] = []
                        missing[user_id].append(current)
                current += timedelta(days=1)
            
            logger.debug(f"Missing submissions: {missing}")
            return missing
            
        except Exception as e:
            logger.error(f"Error getting missed submissions: {str(e)}")
            logger.error(traceback.format_exc())
            return {}

    def _get_active_users(self):
        """Get list of active users"""
        try:
            # Import slack_bot here to avoid circular import
            from slack_client import SlackClient
            slack_client = SlackClient(Config.SLACK_BOT_OAUTH_TOKEN)
            channel_members = slack_client.get_channel_members(Config.SLACK_CHANNEL)
            
            if not channel_members:
                logger.error("No active users found in channel")
                return []
            
            logger.info(f"Found {len(channel_members)} active users in channel")
            return channel_members
            
        except Exception as e:
            logger.error(f"Error getting active users: {str(e)}")
            logger.error(traceback.format_exc())
            return []

    def get_reports_for_date_range(self, start_date, end_date):
        """Get all reports between two dates"""
        try:
            reports = []
            docs = self.db.collection('eod_reports')\
                .where('timestamp', '>=', start_date)\
                .where('timestamp', '<=', end_date)\
                .stream()
            
            for doc in docs:
                report = doc.to_dict()
                report['id'] = doc.id  # Add document ID to report
                reports.append(report)
            
            logger.info(f"Retrieved {len(reports)} reports between {start_date} and {end_date}")
            return reports
        except Exception as e:
            logger.error(f"Error getting reports for date range: {str(e)}")
            return []
