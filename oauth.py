from flask import Blueprint, session, redirect, request, jsonify
from google_auth_oauthlib.flow import Flow
from config import Config

oauth_bp = Blueprint('oauth_bp', __name__)

SCOPES = Config.SCOPES
CLIENT_SECRETS_FILE = Config.CLIENT_SECRETS_FILE
REDIRECT_URI = Config.REDIRECT_URI

@oauth_bp.route('/auth/google')
def login_oauth():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    auth_url, state = flow.authorization_url(prompt='consent')
    session['state'] = state
    return redirect(auth_url)

@oauth_bp.route('/oauth2callback')
def oauth2callback():
    state = session.get('state')
    if not state:
        return "Session expired.", 400
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

@oauth_bp.route('/drive-status')
def drive_status():
    return jsonify({'connected': 'credentials' in session})