from flask import Blueprint, session, redirect, request, jsonify
from google_auth_oauthlib.flow import Flow
from config import Config

# Set the correct prefix so all routes live under /auth/google
oauth_bp = Blueprint('oauth_bp', __name__, url_prefix='/auth/google')

SCOPES = Config.SCOPES
CLIENT_SECRETS_FILE = Config.CLIENT_SECRETS_FILE
REDIRECT_URI = Config.REDIRECT_URI  # Should match Google Console exactly

@oauth_bp.route('', methods=['GET'])
def login_oauth():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    auth_url, state = flow.authorization_url(prompt='consent')
    session['state'] = state
    return redirect(auth_url)

@oauth_bp.route('/callback', methods=['GET'])
def oauth2callback():
    state = session.get('state')
    if not state:
        return "Session expired or invalid.", 400

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        state=state
    )
    flow.fetch_token(authorization_response=request.url)

    creds = flow.credentials
    session['credentials'] = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }

    return redirect('/dashboard')

@oauth_bp.route('/drive-status', methods=['GET'])
def drive_status():
    return jsonify({'connected': 'credentials' in session})
