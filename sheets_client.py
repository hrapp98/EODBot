from google.oauth2 import service_account
from googleapiclient.discovery import build
from config import Config
from firebase_client import FirebaseClient
import logging
from datetime import datetime, timedelta, date
import json
from zoneinfo import ZoneInfo
import traceback

logger = logging.getLogger(__name__)

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
                service_account_info, scopes=SCOPES)

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
                range=f"{Config.SUBMISSIONS_SHEET}!A1:Z1").execute()

            if not result.get('values'):
                # Set headers exactly matching Slack prompts
                headers = [
                    'Timestamp', 'Date', 'Name', 'Email',
                    'Short-term Projects', 'Long-term Projects', 'Blockers',
                    'Next Day Goals', 'Tools Used', 'Help Needed',
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
                body={
                    'values': [headers]
                }).execute()

            # Get sheet ID for submissions sheet
            sheet_metadata = self.service.spreadsheets().get(
                spreadsheetId=self.sheet_id).execute()
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
                                'backgroundColor': {
                                    'red': 0.95,
                                    'green': 0.95,
                                    'blue': 0.95
                                },
                                'textFormat': {
                                    'bold': True
                                },
                                'horizontalAlignment': 'CENTER',
                                'verticalAlignment': 'MIDDLE'
                            }
                        },
                        'fields':
                        'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)'
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
                spreadsheetId=self.sheet_id, body={
                    'requests': requests
                }).execute()

        except Exception as e:
            logger.error(f"Error updating sheet formatting: {str(e)}")

    def update_submissions(self, report_data):
        """Update submissions sheet with new report"""
        if not self.service:
            logger.error("Sheets service not initialized")
            return

        try:
            # Special handling for the two Reys
            rey_id_mapping = {
                "U08KYLRC8KT": "Rey Cucio",  # Rey 1
            }

            user_id = report_data.get('user_id')

            # Get user info from Slack
            try:
                # Check if this is one of the Reys first
                if user_id in rey_id_mapping:
                    user_name = rey_id_mapping[user_id]
                    user_email = f"{user_name.lower().replace(' ', '.')}@example.com"  # Generate email from name
                    logger.info(
                        f"Using mapped name for Rey: {user_name} for user_id: {user_id}"
                    )
                else:
                    from slack_client import SlackClient
                    slack_client = SlackClient(Config.SLACK_BOT_OAUTH_TOKEN)
                    user_info = slack_client.get_user_info(user_id)
                    user_name = user_info.get(
                        'real_name', 'Unknown') if user_info else 'Unknown'
                    user_email = user_info.get('profile', {}).get(
                        'email', 'Unknown') if user_info else 'Unknown'
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
                timestamp_str, date_str, user_name, user_email, short_term,
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
                range=f"{Config.SUBMISSIONS_SHEET}!A:D").execute()

            existing_rows = result.get('values', [])
            row_to_update = None

            for i, existing_row in enumerate(existing_rows):
                if (len(existing_row) >= 4 and existing_row[2] == user_name
                        and existing_row[1] == date_str):
                    row_to_update = i + 1
                    break

            if row_to_update:
                # Update existing row
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.sheet_id,
                    range=f"{Config.SUBMISSIONS_SHEET}!A{row_to_update}",
                    valueInputOption='RAW',
                    body={
                        'values': [row]
                    }).execute()
            else:
                # Append new row
                self.service.spreadsheets().values().append(
                    spreadsheetId=self.sheet_id,
                    range=f"{Config.SUBMISSIONS_SHEET}!A2",
                    valueInputOption='RAW',
                    insertDataOption='INSERT_ROWS',
                    body={
                        'values': [row]
                    }).execute()

        except Exception as e:
            logger.error(f"Error updating submissions sheet: {str(e)}")

    def update_tracker(self):
        """Update submission tracker sheet with complete historical data"""
        if not self.service:
            logger.error("Sheets service not initialized")
            return

        try:
            # Get today's date
            today = datetime.now(ZoneInfo("America/New_York")).date()

            # Get all submissions from Firebase
            if not (self.firebase_client and self.firebase_client.db):
                logger.error(
                    "Firebase client not initialized or database not accessible"
                )
                return

            # Get all users who have ever submitted
            users = set()
            all_submissions = {}  # Dict of date -> set of users who submitted
            all_dates = set()  # Track all dates with submissions

            # Query ALL submissions (no date filtering)
            docs = self.firebase_client.db.collection('eod_reports').stream()

            for doc in docs:
                data = doc.to_dict()
                user_id = data.get('user_id')
                timestamp = data.get('timestamp')

                if not timestamp:
                    continue

                submit_date = timestamp.astimezone(
                    ZoneInfo("America/New_York")).date()
                all_dates.add(submit_date)  # Track this date

                # Get user name
                if 'user_name' not in data:
                    try:
                        from slack_client import SlackClient
                        slack_client = SlackClient(
                            Config.SLACK_BOT_OAUTH_TOKEN)
                        user_info = slack_client.get_user_info(user_id)
                        user_name = user_info.get(
                            'real_name', 'Unknown') if user_info else 'Unknown'
                    except Exception as e:
                        logger.error(f"Error getting user info: {str(e)}")
                        user_name = 'Unknown'
                else:
                    user_name = data.get('user_name')

                users.add(user_name)
                if submit_date not in all_submissions:
                    all_submissions[submit_date] = set()
                all_submissions[submit_date].add(user_name)

            # Create headers (contractor names)
            headers = ['Date'] + sorted(list(users))

            # Generate rows for ALL dates from earliest submission to today
            new_rows = []

            # Find earliest date with submission
            earliest_date = min(all_dates) if all_dates else today

            # Generate a row for every date from earliest to today
            current = earliest_date
            while current <= today:
                row = [current.strftime('%Y-%m-%d')]
                submitted_users = all_submissions.get(current, set())

                for user in headers[1:]:
                    if self._is_holiday(current):
                        row.append('🏖️')  # Holiday
                    elif self._is_weekend(current):
                        row.append('⚫')  # Weekend
                    elif user in submitted_users:
                        row.append('✓')  # Submitted
                    else:
                        row.append('❌')  # Not submitted

                new_rows.append(row)
                current += timedelta(days=1)

            # Sort rows by date in reverse chronological order (newest first)
            new_rows.sort(key=lambda x: x[0], reverse=True)

            # Update sheet with complete data
            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range='Submission Tracker!A1',
                valueInputOption='RAW',
                body={
                    'values': [headers] + new_rows
                }).execute()

            logger.info(
                f"Successfully updated tracker sheet with {len(new_rows)} days of data"
            )

        except Exception as e:
            logger.error(f"Error updating tracker sheet: {str(e)}")
            logger.error(traceback.format_exc())

    def _is_weekend(self, check_date):
        """Check if a date is a weekend"""
        return check_date.weekday() >= 5  # Saturday = 5, Sunday = 6

    def _is_holiday(self, check_date):
        """Check if a date is a holiday"""
        return check_date in HOLIDAYS

    def append_weekly_summary(self, user_id, summary, start_date, end_date):
        """Append weekly summary to the weekly summaries sheet"""
        if not self.service:
            logger.error("Sheets service not initialized")
            return

        try:
            # Special handling for the two Reys
            rey_id_mapping = {
                "U08KYLRC8KT": "Rey Cucio",  # Rey 1
            }

            # Get user info from Slack
            try:
                # Check if this is one of the Reys first
                if user_id in rey_id_mapping:
                    user_name = rey_id_mapping[user_id]
                    user_email = f"{user_name.lower().replace(' ', '.')}@example.com"  # Generate email from name
                    logger.info(
                        f"Using mapped name for Rey: {user_name} for user_id: {user_id}"
                    )
                else:
                    from slack_client import SlackClient
                    slack_client = SlackClient(Config.SLACK_BOT_OAUTH_TOKEN)
                    user_info = slack_client.get_user_info(user_id)
                    user_name = user_info.get(
                        'real_name', 'Unknown') if user_info else 'Unknown'
                    user_email = user_info.get('profile', {}).get(
                        'email', 'Unknown') if user_info else 'Unknown'
            except Exception as e:
                logger.error(f"Error getting Slack user info: {str(e)}")
                user_name = 'Unknown'
                user_email = 'Unknown'

            # Format dates
            date_range = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
            timestamp = datetime.now(
                ZoneInfo("America/New_York")).strftime('%Y-%m-%d %H:%M:%S')

            # Prepare row data
            row = [timestamp, date_range, user_name, user_email, summary]

            # Append to weekly summaries sheet
            range_name = f"{Config.WEEKLY_SUMMARIES_SHEET}!A:E"
            body = {'values': [row]}
            self.service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range=range_name,
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body=body).execute()

            logger.info(f"Added weekly summary for {user_name} to sheets")
        except Exception as e:
            logger.error(f"Error appending weekly summary to sheets: {str(e)}")

    def update_tracker_sheet(self, firebase_client=None):
        """Update submission tracker sheet with complete historical data"""
        if not self.service:
            logger.error("Sheets service not initialized")
            return

        try:
            # Use the passed firebase_client if provided, otherwise use self.firebase_client
            fb_client = firebase_client if firebase_client else self.firebase_client

            # Check if Firebase client is initialized
            if not fb_client or not fb_client.db:
                logger.error(
                    "Firebase client not initialized or database not accessible"
                )
                return

            # Get today's date
            today = datetime.now(ZoneInfo("America/New_York")).date()

            # Get all submissions from Firebase
            docs = list(fb_client.db.collection('eod_reports').stream())
            logger.info(f"Retrieved {len(docs)} documents from Firebase")

            # Process submission data
            all_dates = set()
            all_submissions = {}
            users = set()

            # Track user IDs to filter out bots and deactivated users
            user_id_to_name = {}

            # Special handling for the two Reys
            rey_id_mapping = {
                "U08KYLRC8KT": "Rey Cucio",  # Rey 1
            }

            logger.info("Processing submission data")
            submission_count = 0
            for doc in docs:
                submission_count += 1
                data = doc.to_dict()
                user_id = data.get('user_id')
                timestamp = data.get('timestamp')

                logger.info(
                    f"Processing document {doc.id}: user_id={user_id}, timestamp={timestamp}"
                )

                # Skip internal team members
                if user_id in INTERNAL_TEAM_IDS:
                    logger.info(f"Skipping internal team member: {user_id}")
                    continue

                if not timestamp:
                    logger.warning(
                        f"Skipping document with missing timestamp: {doc.id}")
                    continue

                # Log the timestamp type and value
                logger.info(
                    f"Timestamp type: {type(timestamp)}, value: {timestamp}")

                try:
                    submit_date = timestamp.astimezone(
                        ZoneInfo("America/New_York")).date()
                    logger.info(f"Converted timestamp to date: {submit_date}")
                except Exception as e:
                    logger.error(
                        f"Error converting timestamp to date: {str(e)}")
                    logger.error(f"Timestamp value: {timestamp}")
                    continue

                all_dates.add(submit_date)  # Track this date

                # Get user name and check if bot or deactivated
                try:
                    # Special handling for the two Reys
                    if user_id in rey_id_mapping:
                        user_name = rey_id_mapping[user_id]
                        logger.info(
                            f"Using mapped name for Rey: {user_name} for user_id: {user_id}"
                        )
                    else:
                        from slack_client import SlackClient
                        slack_client = SlackClient(
                            Config.SLACK_BOT_OAUTH_TOKEN)
                        user_info = slack_client.get_user_info(user_id)

                        # Skip if user is a bot
                        if user_info and user_info.get('is_bot', False):
                            logger.info(f"Skipping bot user: {user_id}")
                            continue

                        # Skip if user is deactivated
                        if user_info and user_info.get('deleted', False):
                            logger.info(
                                f"Skipping deactivated user: {user_id}")
                            continue

                        user_name = user_info.get(
                            'real_name', 'Unknown') if user_info else data.get(
                                'user_name', 'Unknown')
                        logger.info(
                            f"Retrieved user name: {user_name} for user_id: {user_id}"
                        )

                    # Store user ID to name mapping
                    user_id_to_name[user_id] = user_name

                except Exception as e:
                    logger.error(f"Error getting user info: {str(e)}")
                    user_name = data.get('user_name', 'Unknown')

                users.add(user_name)
                if submit_date not in all_submissions:
                    all_submissions[submit_date] = set()
                all_submissions[submit_date].add(user_name)
                logger.info(
                    f"Added {user_name} to submissions for {submit_date}")

            logger.info(
                f"Processed {submission_count} submissions from {len(users)} users"
            )
            logger.info(f"All dates with submissions: {sorted(all_dates)}")
            logger.info(
                f"Submission dates in tracking dict: {sorted(all_submissions.keys())}"
            )
            logger.info(f"Users who submitted: {sorted(users)}")

            # Create headers (contractor names)
            headers = ['Date'] + sorted(list(users))
            logger.info(
                f"Created headers with {len(headers)} columns: {headers}")

            # Generate rows for ALL dates from earliest submission to today
            new_rows = []

            # Find earliest date with submission
            earliest_date = min(all_dates) if all_dates else today
            logger.info(f"Earliest date with submission: {earliest_date}")

            # Generate a row for every date from earliest to today
            current = earliest_date
            date_count = 0
            logger.info(f"Generating rows from {earliest_date} to {today}")

            while current <= today:
                date_count += 1
                row = [current.strftime('%Y-%m-%d')]
                submitted_users = all_submissions.get(current, set())
                logger.info(
                    f"For date {current}, submitted users: {sorted(submitted_users) if submitted_users else 'None'}"
                )

                for user in headers[1:]:
                    if self._is_holiday(current):
                        row.append('🏖️')  # Holiday
                        logger.info(
                            f"Marking holiday for user {user} on {current}")
                    elif self._is_weekend(current):
                        row.append('⚫')  # Weekend
                        logger.info(
                            f"Marking weekend for user {user} on {current}")
                    elif user in submitted_users:
                        row.append('✓')  # Submitted
                        logger.info(f"User {user} submitted for {current}")
                    else:
                        row.append('❌')  # Not submitted
                        logger.info(
                            f"User {user} did NOT submit for {current}")

                new_rows.append(row)
                current += timedelta(days=1)

            logger.info(f"Generated {date_count} rows of data")

            # Ensure newest date is at the top
            new_rows.reverse()
            logger.info("Reversed rows to ensure newest date is at the top")

            # Update sheet
            logger.info(
                f"Updating Google Sheet with {len(new_rows)} rows of data")
            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range='Submission Tracker!A1',
                valueInputOption='RAW',
                body={
                    'values': [headers] + new_rows
                }).execute()

            logger.info("Tracker sheet update complete")
        except Exception as e:
            logger.error(f"Error updating tracker sheet: {str(e)}")
            logger.error(traceback.format_exc())
