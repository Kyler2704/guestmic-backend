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
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB

    # OAuth2 settings
    SCOPES = [os.getenv('OAUTH2_SCOPE', '')]
    CLIENT_SECRETS_FILE = os.getenv('CLIENT_SECRET', '')
    REDIRECT_URI = os.getenv('REDIRECT_URI', '')