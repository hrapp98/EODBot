from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime
from models import EODReport, Contractor

class GoogleSheetsService:
    def __init__(self):
        self.SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        self.SPREADSHEET_ID = 'your-spreadsheet-id'
        self.credentials = service_account.Credentials.from_service_account_info(
            {
                # Add your service account credentials here
            },
            scopes=self.SCOPES
        )
        self.service = build('sheets', 'v4', credentials=self.credentials)

    def export_daily_reports(self):
        """Export daily EOD reports to Google Sheets"""
        try:
            reports = EODReport.query.filter(
                EODReport.date == datetime.utcnow().date()
            ).all()
            
            values = []
            for report in reports:
                contractor = Contractor.query.get(report.contractor_id)
                values.append([
                    str(report.date),
                    contractor.name,
                    report.short_term_work,
                    report.long_term_work,
                    str(report.short_term_progress),
                    str(report.long_term_progress),
                    report.accomplishments,
                    report.blockers,
                    report.next_day_goals,
                    report.client_interactions
                ])
            
            body = {
                'values': values
            }
            
            self.service.spreadsheets().values().append(
                spreadsheetId=self.SPREADSHEET_ID,
                range='Daily Reports!A:J',
                valueInputOption='RAW',
                body=body
            ).execute()
            
        except Exception as e:
            raise Exception(f"Error exporting to Google Sheets: {e}")

    def update_submission_tracker(self):
        """Update the submission tracker sheet"""
        try:
            contractors = Contractor.query.all()
            today = datetime.utcnow().date()
            
            values = []
            for contractor in contractors:
                report = EODReport.query.filter_by(
                    contractor_id=contractor.id,
                    date=today
                ).first()
                
                values.append([
                    contractor.name,
                    str(today),
                    'Yes' if report else 'No'
                ])
            
            body = {
                'values': values
            }
            
            self.service.spreadsheets().values().update(
                spreadsheetId=self.SPREADSHEET_ID,
                range='Submission Tracker!A:C',
                valueInputOption='RAW',
                body=body
            ).execute()
            
        except Exception as e:
            raise Exception(f"Error updating submission tracker: {e}")
