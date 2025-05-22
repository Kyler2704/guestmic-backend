import os
import logging
from pathlib import Path

import firebase_admin
from firebase_admin import credentials as fb_credentials, firestore, storage as fb_storage, auth as fb_auth

logger = logging.getLogger(__name__)

# Determine path to service account JSON
cred_env = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '')
if not cred_env:
    logger.error("GOOGLE_APPLICATION_CREDENTIALS not set")
cred_path = Path(cred_env)
if not cred_path.is_absolute():
    # Relative paths are resolved against this file's directory
    cred_path = Path(__file__).parent / cred_env

logger.info("Loading Firebase credentials from %s (exists=%s)", cred_path, cred_path.exists())

# Initialize Firebase Admin SDK
cred = fb_credentials.Certificate(str(cred_path))
firebase_admin.initialize_app(cred, {
    'storageBucket': os.getenv('STORAGE_BUCKET', '')
})

# Expose Firestore client, Storage bucket, and Auth API
db = firestore.client()
bucket = fb_storage.bucket()
firebase_auth = fb_auth