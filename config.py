import os
from dotenv import load_dotenv

load_dotenv()

# Allow HTTP for OAuth in non-prod
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', '')
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.getenv('FLASK_ENV') == 'production'
    SESSION_COOKIE_SAMESITE = 'Lax'
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32 MB — accommodates 2-min WebM chunks

    # OAuth2 settings
    SCOPES = [
        'openid',
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile',
        'https://www.googleapis.com/auth/drive.file'
    ]
    CLIENT_SECRETS_FILE = os.getenv('CLIENT_SECRET', '')
    REDIRECT_URI = os.getenv('REDIRECT_URI', '')

