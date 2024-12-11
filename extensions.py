"""
Firebase database configuration and initialization.
All database operations are handled through Firebase Firestore.
"""

from firebase_admin import credentials, firestore, initialize_app
import json
import logging

logger = logging.getLogger(__name__)

def init_firebase(config):
    """Initialize Firebase with the provided configuration."""
    try:
        # Initialize Firebase Admin SDK
        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": config.FIREBASE_PROJECT_ID,
            "private_key_id": config.FIREBASE_API_KEY,
            "private_key": config.FIREBASE_PRIVATE_KEY.replace('\\n', '\n'),
            "client_email": config.FIREBASE_CLIENT_EMAIL,
        })
        
        firebase_app = initialize_app(cred)
        db = firestore.client()
        logger.info("Firebase initialized successfully")
        return db
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {str(e)}")
        return None
