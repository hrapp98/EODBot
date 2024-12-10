import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from config import Config

class FirebaseClient:
    def __init__(self):
        # Initialize Firebase Admin SDK with configuration
        if not firebase_admin._apps:
            config = {
                'apiKey': Config.FIREBASE_API_KEY,
                'appId': Config.FIREBASE_APP_ID,
                'projectId': Config.FIREBASE_PROJECT_ID,
                'storageBucket': Config.FIREBASE_STORAGE_BUCKET
            }
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, config)
        self.db = firestore.client()

    def save_eod_report(self, user_id, report_data):
        """Save EOD report to Firebase"""
        report_data['timestamp'] = datetime.now()
        doc_ref = self.db.collection('eod_reports').document()
        doc_ref.set(report_data)
        return doc_ref.id

    def get_user_reports(self, user_id, date=None):
        """Get EOD reports for a specific user"""
        query = self.db.collection('eod_reports').where('user_id', '==', user_id)
        if date:
            query = query.where('timestamp', '>=', date)
        return [doc.to_dict() for doc in query.stream()]

    def get_missing_reports(self, date):
        """Get list of users who haven't submitted reports for a given date"""
        query = self.db.collection('eod_reports').where('timestamp', '>=', date)
        submitted_users = set(doc.get('user_id') for doc in query.stream())
        # Note: In production, we'd compare this against a list of all users
        return submitted_users

    def save_tracker(self, tracker_data):
        """Save submission tracker to Firebase"""
        doc_ref = self.db.collection('submission_trackers').document()
        doc_ref.set(tracker_data)
        return doc_ref.id

    def get_tracker(self, user_id, date):
        """Get tracker for a specific user and date"""
        query = self.db.collection('submission_trackers').where('user_id', '==', user_id).where('date', '==', date)
        docs = list(query.stream())
        return docs[0].to_dict() if docs else None
