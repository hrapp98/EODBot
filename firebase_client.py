import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import json
import logging
from config import Config

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
                
                # Load and format private key
                private_key = Config.FIREBASE_APP_ID
                if not private_key:
                    logger.error("Firebase private key is missing")
                    return
                    
                # Handle various private key formats
                if '\\n' in private_key:
                    private_key = private_key.replace('\\n', '\n')
                elif r'\n' in private_key:
                    private_key = private_key.replace(r'\n', '\n')
                
                # Create service account info
                service_account_info = {
                    "type": "service_account",
                    "project_id": Config.FIREBASE_PROJECT_ID,
                    "private_key_id": Config.FIREBASE_API_KEY,
                    "private_key": private_key,
                    "client_email": f"firebase-adminsdk-{Config.FIREBASE_PROJECT_ID}@{Config.FIREBASE_PROJECT_ID}.iam.gserviceaccount.com",
                    "client_id": "",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-{Config.FIREBASE_PROJECT_ID}%40{Config.FIREBASE_PROJECT_ID}.iam.gserviceaccount.com"
                }
                
                logger.debug(f"Project ID: {Config.FIREBASE_PROJECT_ID}")
                logger.debug(f"Private key format check: {private_key.startswith('-----BEGIN PRIVATE KEY-----')}")
                
                try:
                    logger.debug("Attempting to initialize Firebase with credentials...")
                    cred = credentials.Certificate(service_account_info)
                    firebase_admin.initialize_app(cred)
                    logger.info("Firebase app initialized successfully")
                except ValueError as ve:
                    logger.error(f"Invalid credential format: {str(ve)}")
                    return
                except Exception as e:
                    logger.error(f"Failed to initialize Firebase app: {str(e)}")
                    return
            
            try:
                self.db = firestore.client()
                logger.info("Firestore client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Firestore client: {str(e)}")
                self.db = None
                
        except Exception as e:
            logger.error(f"Unexpected error in Firebase initialization: {str(e)}")
            self.db = None

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
