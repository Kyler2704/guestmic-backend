import requests
from flask import Blueprint, session, redirect, request, jsonify, current_app
from google_auth_oauthlib.flow import Flow
from config import Config

# All OAuth routes live under /auth/google
oauth_bp = Blueprint('oauth_bp', __name__, url_prefix='/auth/google')

SCOPES               = Config.SCOPES
CLIENT_SECRETS_FILE  = Config.CLIENT_SECRETS_FILE
REDIRECT_URI         = Config.REDIRECT_URI  # e.g. "https://guestmic-backend.onrender.com/auth/google/callback"

@oauth_bp.route('/auth/google')
def login_oauth():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes=True,  # ← preserve all scopes
        prompt='consent'
    )
    session['state'] = state
    return redirect(auth_url)


@oauth_bp.route('/callback', methods=['GET'])
def oauth2callback():
    """
    Step 2: Handle Google's redirect back to our app.
    """
    incoming_state = request.args.get('state')
    saved_state    = session.get('state')

    if not saved_state or incoming_state != saved_state:
        current_app.logger.warning(f"State mismatch: incoming={incoming_state}, saved={saved_state}")
        return "Session expired or invalid. Please try again.", 400

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        state=saved_state
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
    session.pop('state', None)
    current_app.logger.debug("OAuth credentials saved in session.")

    # Redirect to your front-end dashboard
    return redirect('https://guestmic.web.app/GuestMicDashboard.html')


@oauth_bp.route('/drive-status', methods=['GET'])
def drive_status():
    """
    Check if the user has authorized Google Drive.
    """
    return jsonify({'connected': 'credentials' in session})


@oauth_bp.route('/userinfo', methods=['GET'])
def userinfo():
    """
    Fetch the logged-in user's Google profile info.
    """
    creds_data = session.get('credentials')
    if not creds_data:
        return jsonify({'error': 'Unauthorized'}), 401

    resp = requests.get(
        'https://www.googleapis.com/oauth2/v3/userinfo',
        headers={'Authorization': f"Bearer {creds_data['token']}"}
    )
    if not resp.ok:
        current_app.logger.error(f"Userinfo failed: {resp.text}")
        return jsonify({'error': 'Could not fetch user info'}), 500

    return jsonify(resp.json()), 200

@oauth_bp.route('/auth/google/userinfo')
def google_userinfo():
    """Return basic profile info for the connected Google Drive account."""
    creds = session.get('credentials')
    if not creds:
        return jsonify({'error': 'Unauthorized'}), 401

    token = creds.get('token')
    try:
        resp = requests.get(
            'https://www.googleapis.com/oauth2/v1/userinfo',
            params={'alt': 'json'},
            headers={'Authorization': f'Bearer {token}'}
        )
        resp.raise_for_status()
        return jsonify(resp.json()), 200
    except Exception as e:
        current_app.logger.error(f"Userinfo fetch failed: {e}")
        return jsonify({'error': 'Could not fetch userinfo'}), 500
