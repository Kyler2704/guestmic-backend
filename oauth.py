import requests
from flask import Blueprint, session, redirect, request, jsonify, current_app
from google_auth_oauthlib.flow import Flow
from config import Config
from fb_admin import db

# OAuth Blueprint with no prefix to expose routes at root
oauth_bp = Blueprint('oauth_bp', __name__)

SCOPES = Config.SCOPES
CLIENT_SECRETS_FILE = Config.CLIENT_SECRETS_FILE
REDIRECT_URI = Config.REDIRECT_URI  # e.g. https://guestmic-backend.onrender.com/auth/google/callback

@oauth_bp.route('/auth/google')
def login_oauth():
    # Accept optional uid query param from the dashboard so we can
    # associate Drive credentials with the correct Firestore user doc.
    uid = request.args.get('uid', '').strip()
    if uid:
        session['uid'] = uid

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    session['state'] = state
    return redirect(auth_url)

@oauth_bp.route('/auth/google/callback')
def oauth2callback():
    """
    Handle OAuth2 callback, store credentials in session, and persist
    them to Firestore so background threads can retrieve them by ownerUid.
    """
    incoming_state = request.args.get('state')
    saved_state = session.get('state')
    if not saved_state or incoming_state != saved_state:
        current_app.logger.warning(
            f"State mismatch: incoming={incoming_state}, saved={saved_state}"
        )
        return "Session expired or invalid. Please try again.", 400

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        state=saved_state
    )
    # Render terminates TLS at the proxy level, so request.url arrives as
    # http:// even though the client used https://. Google rejects the token
    # exchange if the redirect URI doesn't match exactly. Force https here.
    auth_response = request.url
    if auth_response.startswith('http://'):
        auth_response = 'https://' + auth_response[7:]
    flow.fetch_token(authorization_response=auth_response)

    creds = flow.credentials
    creds_dict = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes or []),
    }

    # Keep session-based access for same-request use
    session['credentials'] = creds_dict
    session.pop('state', None)
    current_app.logger.debug("OAuth credentials saved in session.")

    # Persist to Firestore so the background merge thread can retrieve
    # credentials by ownerUid without access to the request session.
    uid = session.get('uid')
    if uid:
        db.collection('users').document(uid).set(
            {'driveCredentials': creds_dict},
            merge=True
        )
        current_app.logger.debug("Drive credentials persisted to Firestore for uid=%s", uid)
    else:
        current_app.logger.warning(
            "No uid in session at OAuth callback — Drive credentials not persisted to Firestore. "
            "Ensure the dashboard passes ?uid=<firebase_uid> when initiating /auth/google."
        )

    # Redirect to front-end dashboard
    return redirect('https://guestmic.web.app/GuestMicDashboard.html')

@oauth_bp.route('/drive-status')
def drive_status():
    """
    Check if Google Drive OAuth credentials are present.
    """
    return jsonify({'connected': 'credentials' in session})

@oauth_bp.route('/auth/google/userinfo')
def google_userinfo():
    """
    Fetch the connected Google account's profile info.
    """
    creds = session.get('credentials')
    if not creds:
        return jsonify({'error': 'Unauthorized'}), 401

    token = creds.get('token')
    try:
        resp = requests.get(
            'https://www.googleapis.com/oauth2/v3/userinfo',
            headers={'Authorization': f'Bearer {token}'}
        )
        resp.raise_for_status()
        return jsonify(resp.json()), 200
    except Exception as e:
        current_app.logger.error(f"Userinfo fetch failed: {e}")
        return jsonify({'error': 'Could not fetch userinfo'}), 500
