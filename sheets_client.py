from google.oauth2 import service_account
from googleapiclient.discovery import build
from config import Config
from firebase_client import FirebaseClient
import logging
from datetime import datetime, timedelta
import json
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

class SheetsClient:
    def __init__(self):
        self.service = self._get_sheets_service()
        self.sheet_id = Config.SHEET_ID
        
        # Initialize Firebase client
        self.firebase_client = None
        if Config.firebase_config_valid():
            self.firebase_client = FirebaseClient()
        
        # Initialize headers if needed
        self._init_headers()
    
    def _get_sheets_service(self):
        """Initialize Google Sheets API service"""
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        
        try:
            # Load service account info from environment
            service_account_info = json.loads(Config.GOOGLE_SERVICE_ACCOUNT)
            
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=SCOPES
            )
            
            return build('sheets', 'v4', credentials=credentials)
            
        except Exception as e:
            logger.error(f"Error initializing sheets service: {str(e)}")
            return None
    
    def _init_headers(self):
        """Initialize sheet headers if they don't exist"""
        try:
            # Check if headers exist
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=f"{Config.SUBMISSIONS_SHEET}!A1:Z1"
            ).execute()
            
            if not result.get('values'):
                # Set headers exactly matching Slack prompts
                headers = [
                    'Timestamp',
                    'Date',
                    'Name',
                    'Email',
                    'Short-term Projects',
                    'Long-term Projects',
                    'Blockers',
                    'Next Day Goals',
                    'Tools Used',
                    'Help Needed',
                    'Client Feedback'
                ]
                
                # Update headers and format
                self._update_sheet_formatting(headers)

        except Exception as e:
            logger.error(f"Error initializing headers: {str(e)}")

    def _update_sheet_formatting(self, headers):
        """Update sheet formatting with headers"""
        try:
            # Update headers
            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=f"{Config.SUBMISSIONS_SHEET}!A1",
                valueInputOption='RAW',
                body={'values': [headers]}
            ).execute()

            # Get sheet ID for submissions sheet
            sheet_metadata = self.service.spreadsheets().get(
                spreadsheetId=self.sheet_id
            ).execute()
            sheet_id = None
            for sheet in sheet_metadata.get('sheets', ''):
                if sheet['properties']['title'] == Config.SUBMISSIONS_SHEET:
                    sheet_id = sheet['properties']['sheetId']
                    break

            if not sheet_id:
                logger.error("Could not find submissions sheet ID")
                return

            # Format requests
            requests = [
                # Header formatting
                {
                    'repeatCell': {
                        'range': {
                            'sheetId': sheet_id,
                            'startRowIndex': 0,
                            'endRowIndex': 1
                        },
                        'cell': {
                            'userEnteredFormat': {
                                'backgroundColor': {'red': 0.95, 'green': 0.95, 'blue': 0.95},
                                'textFormat': {'bold': True},
                                'horizontalAlignment': 'CENTER',
                                'verticalAlignment': 'MIDDLE'
                            }
                        },
                        'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)'
                    }
                },
                # Column widths
                {
                    'updateDimensionProperties': {
                        'range': {
                            'sheetId': sheet_id,
                            'dimension': 'COLUMNS',
                            'startIndex': 0,
                            'endIndex': len(headers)
                        },
                        'properties': {
                            'pixelSize': 200
                        },
                        'fields': 'pixelSize'
                    }
                },
                # Freeze header row
                {
                    'updateSheetProperties': {
                        'properties': {
                            'sheetId': sheet_id,
                            'gridProperties': {
                                'frozenRowCount': 1
                            }
                        },
                        'fields': 'gridProperties.frozenRowCount'
                    }
                }
            ]

            # Apply formatting
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id,
                body={'requests': requests}
            ).execute()

        except Exception as e:
            logger.error(f"Error updating sheet formatting: {str(e)}")

    def update_submissions(self, report_data):
        """Update submissions sheet with new report"""
        if not self.service:
            logger.error("Sheets service not initialized")
            return
        
        try:
            # Get user info from Slack
            try:
                from slack_client import SlackClient
                slack_client = SlackClient(Config.SLACK_BOT_OAUTH_TOKEN)
                user_info = slack_client.get_user_info(report_data.get('user_id'))
                user_name = user_info.get('real_name', 'Unknown') if user_info else 'Unknown'
                user_email = user_info.get('profile', {}).get('email', 'Unknown') if user_info else 'Unknown'
            except Exception as e:
                logger.error(f"Error getting Slack user info: {str(e)}")
                user_name = 'Unknown'
                user_email = 'Unknown'

            # Format timestamp and date
            now = datetime.now(ZoneInfo("America/New_York"))
            date_str = now.strftime('%Y-%m-%d')
            timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')

            # Get project data directly from the form values
            short_term = report_data.get('short_term_projects', '')
            long_term = report_data.get('long_term_projects', '')
            
            # Convert report data to row format
            row = [
                timestamp_str,
                date_str,
                user_name,
                user_email,
                short_term,
                long_term,
                report_data.get('blockers', ''),
                report_data.get('next_day_goals', ''),
                report_data.get('tools_used', ''),
                report_data.get('help_needed', ''),
                report_data.get('client_feedback', '')
            ]

            # Find existing row for today if it exists
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=f"{Config.SUBMISSIONS_SHEET}!A:D"
            ).execute()
            
            existing_rows = result.get('values', [])
            row_to_update = None
            
            for i, existing_row in enumerate(existing_rows):
                if (len(existing_row) >= 4 and 
                    existing_row[2] == user_name and 
                    existing_row[1] == date_str):
                    row_to_update = i + 1
                    break

            if row_to_update:
                # Update existing row
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.sheet_id,
                    range=f"{Config.SUBMISSIONS_SHEET}!A{row_to_update}",
                    valueInputOption='RAW',
                    body={'values': [row]}
                ).execute()
            else:
                # Append new row
                self.service.spreadsheets().values().append(
                    spreadsheetId=self.sheet_id,
                    range=f"{Config.SUBMISSIONS_SHEET}!A2",
                    valueInputOption='RAW',
                    insertDataOption='INSERT_ROWS',
                    body={'values': [row]}
                ).execute()

        except Exception as e:
            logger.error(f"Error updating submissions sheet: {str(e)}")
    
    def update_tracker(self):
        """Update submission tracker sheet"""
        if not self.service:
            logger.error("Sheets service not initialized")
            return
        
        try:
            # Get today's date
            today = datetime.now(ZoneInfo("America/New_York")).date()
            start_date = today - timedelta(days=6)  # Show last 7 days
            
            logger.info(f"Updating tracker for date range: {start_date} to {today}")
            
            # Get all submissions for the date range
            users = set()  # Set of all users
            submissions = {}  # Dict of date -> set of users who submitted
            
            if self.firebase_client and self.firebase_client.db:
                # Convert dates to UTC for Firebase query
                start_datetime = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=ZoneInfo("America/New_York"))
                end_datetime = datetime.combine(today, datetime.max.time()).replace(tzinfo=ZoneInfo("America/New_York"))
                
                logger.info(f"Querying Firebase for submissions between {start_datetime} and {end_datetime}")
                
                # Update to use where() instead of filter()
                docs = self.firebase_client.db.collection('eod_reports')\
                    .where('timestamp', '>=', start_datetime)\
                    .where('timestamp', '<=', end_datetime)\
                    .stream()

                submission_count = 0
                for doc in docs:
                    submission_count += 1
                    data = doc.to_dict()
                    user_id = data.get('user_id')
                    timestamp = data.get('timestamp')
                    
                    if not timestamp:
                        logger.warning(f"Missing timestamp in document {doc.id}")
                        continue
                    
                    submit_date = timestamp.astimezone(ZoneInfo("America/New_York")).date()
                    
                    # Get user name from the document or Slack
                    if 'user_name' not in data:
                        try:
                            from slack_client import SlackClient
                            slack_client = SlackClient(Config.SLACK_BOT_OAUTH_TOKEN)
                            user_info = slack_client.get_user_info(user_id)
                            user_name = user_info.get('real_name', 'Unknown') if user_info else 'Unknown'
                        except Exception as e:
                            logger.error(f"Error getting user info: {str(e)}")
                            user_name = 'Unknown'
                    else:
                        user_name = data.get('user_name')
                    
                    users.add(user_name)
                    if submit_date not in submissions:
                        submissions[submit_date] = set()
                    submissions[submit_date].add(user_name)
                
                logger.info(f"Found {submission_count} submissions for {len(users)} users")
                logger.info(f"Users found: {users}")
                logger.info(f"Submissions by date: {submissions}")

                if not users:
                    logger.warning("No users found in the date range")
                    return

                # Create headers (contractor names)
                headers = ['Date'] + sorted(list(users))
                
                # Create rows (dates with submissions)
                rows = []
                current = start_date
                while current <= today:
                    row = [current.strftime('%Y-%m-%d')]  # First column is date
                    submitted_users = submissions.get(current, set())
                    for user in headers[1:]:  # Skip 'Date' column
                        row.append('✓' if user in submitted_users else '❌')
                    rows.append(row)
                    current += timedelta(days=1)  # Don't forget to increment the date!
                
                logger.info(f"Created {len(rows)} rows with {len(headers)} columns")

                # Clear existing content in tracker sheet
                logger.info("Clearing existing tracker content")
                self.service.spreadsheets().values().clear(
                    spreadsheetId=self.sheet_id,
                    range='Submission Tracker!A1:Z1000'  # Use sheet name directly
                ).execute()

                # Update headers and data
                logger.info("Updating tracker with new data")
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.sheet_id,
                    range='Submission Tracker!A1',  # Use sheet name directly
                    valueInputOption='RAW',
                    body={'values': [headers] + rows}
                ).execute()

                logger.info("Successfully updated tracker sheet")

            else:
                logger.error("Firebase client not initialized or database not accessible")

        except Exception as e:
            logger.error(f"Error updating tracker sheet: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    def append_weekly_summary(self, user_id, summary, start_date, end_date):
        """Append weekly summary to the weekly summaries sheet"""
        if not self.service:
            logger.error("Sheets service not initialized")
            return
        
        try:
            # Get user info from Slack
            try:
                from slack_client import SlackClient
                slack_client = SlackClient(Config.SLACK_BOT_OAUTH_TOKEN)
                user_info = slack_client.get_user_info(user_id)
                user_name = user_info.get('real_name', 'Unknown') if user_info else 'Unknown'
                user_email = user_info.get('profile', {}).get('email', 'Unknown') if user_info else 'Unknown'
            except Exception as e:
                logger.error(f"Error getting Slack user info: {str(e)}")
                user_name = 'Unknown'
                user_email = 'Unknown'

            # Format dates
            date_range = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
            timestamp = datetime.now(ZoneInfo("America/New_York")).strftime('%Y-%m-%d %H:%M:%S')

            # Prepare row data
            row = [
                timestamp,
                date_range,
                user_name,
                user_email,
                summary
            ]

            # Append to weekly summaries sheet
            range_name = f"{Config.WEEKLY_SUMMARIES_SHEET}!A:E"
            body = {
                'values': [row]
            }
            self.service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range=range_name,
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            logger.info(f"Added weekly summary for {user_name} to sheets")
        except Exception as e:
            logger.error(f"Error appending weekly summary to sheets: {str(e)}")
