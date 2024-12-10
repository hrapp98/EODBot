from google.oauth2 import service_account
from googleapiclient.discovery import build
from config import Config
import logging

logger = logging.getLogger(__name__)

class SheetsClient:
    def __init__(self):
        self.service = self._get_sheets_service()
        self.sheet_id = Config.SHEET_ID
    
    def _get_sheets_service(self):
        """Initialize Google Sheets API service"""
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        
        try:
            credentials = service_account.Credentials.from_service_account_file(
                'service-account.json',
                scopes=SCOPES
            )
            
            return build('sheets', 'v4', credentials=credentials)
            
        except Exception as e:
            logger.error(f"Error initializing sheets service: {str(e)}")
            return None
    
    def update_submissions(self, reports):
        """Update submissions sheet with new reports"""
        try:
            values = []
            
            for report in reports:
                values.append([
                    report.created_at.isoformat(),
                    report.user_id,
                    str(report.short_term_projects),
                    str(report.long_term_projects),
                    report.accomplishments,
                    report.blockers,
                    report.next_day_goals,
                    report.client_interactions
                ])
            
            if values:
                body = {
                    'values': values
                }
                
                self.service.spreadsheets().values().append(
                    spreadsheetId=self.sheet_id,
                    range=f"{Config.SUBMISSIONS_SHEET}!A2",
                    valueInputOption='RAW',
                    body=body
                ).execute()
                
        except Exception as e:
            logger.error(f"Error updating submissions sheet: {str(e)}")
    
    def update_tracker(self):
        """Update submission tracker sheet"""
        try:
            from models import SubmissionTracker
            from datetime import datetime, timedelta
            
            # Get last 7 days of tracking data
            start_date = datetime.utcnow().date() - timedelta(days=7)
            trackers = SubmissionTracker.query.filter(
                SubmissionTracker.date >= start_date
            ).all()
            
            # Organize data by user and date
            tracker_data = {}
            for tracker in trackers:
                if tracker.user_id not in tracker_data:
                    tracker_data[tracker.user_id] = {}
                tracker_data[tracker.user_id][tracker.date] = tracker.submitted
            
            # Convert to sheet rows
            values = []
            for user_id, dates in tracker_data.items():
                row = [user_id]
                current = start_date
                
                while current <= datetime.utcnow().date():
                    row.append('Yes' if dates.get(current, False) else 'No')
                    current += timedelta(days=1)
                
                values.append(row)
            
            if values:
                body = {
                    'values': values
                }
                
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.sheet_id,
                    range=f"{Config.TRACKER_SHEET}!A2",
                    valueInputOption='RAW',
                    body=body
                ).execute()
                
        except Exception as e:
            logger.error(f"Error updating tracker sheet: {str(e)}")
