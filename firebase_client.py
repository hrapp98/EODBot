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
        """Save EOD report to Firebase"""
        if not self.db:
            logger.error("Firebase client not initialized")
            return None
            
        try:
            report_data['timestamp'] = datetime.now()
            doc_ref = self.db.collection('eod_reports').document()
            doc_ref.set(report_data)
            return doc_ref.id
        except Exception as e:
            logger.error(f"Error saving EOD report: {str(e)}")
            return None

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
