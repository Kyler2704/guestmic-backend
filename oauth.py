import hashlib
import json
import secrets
import base64
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
    uid = request.args.get('uid', '').strip()

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b'=').decode()

    # Encode uid + code_verifier into state so the callback is stateless —
    # no session needed, survives Render multi-instance redirects.
    state_payload = base64.urlsafe_b64encode(
        json.dumps({'uid': uid, 'cv': code_verifier}).encode()
    ).decode().rstrip('=')

    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
        state=state_payload,
        code_challenge=code_challenge,
        code_challenge_method='S256',
    )
    return redirect(auth_url)

@oauth_bp.route('/auth/google/callback')
def oauth2callback():
    """
    Handle OAuth2 callback, store credentials in session, and persist
    them to Firestore so background threads can retrieve them by ownerUid.
    """
    incoming_state = request.args.get('state', '')
    try:
        # Pad base64 back to a multiple of 4
        padded = incoming_state + '=' * (-len(incoming_state) % 4)
        state_data = json.loads(base64.urlsafe_b64decode(padded).decode())
        uid = state_data.get('uid', '').strip()
        code_verifier = state_data.get('cv', '')
    except Exception:
        current_app.logger.warning("Could not decode state parameter: %s", incoming_state)
        return "Invalid state parameter. Please try again.", 400

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        state=incoming_state,
    )

    auth_response = request.url
    if auth_response.startswith('http://'):
        auth_response = 'https://' + auth_response[7:]

    flow.fetch_token(
        authorization_response=auth_response,
        code_verifier=code_verifier,
    )

    creds = flow.credentials
    creds_dict = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes or []),
        'expiry': creds.expiry.isoformat() if creds.expiry else None,
    }

    session['credentials'] = creds_dict
    current_app.logger.debug("OAuth credentials saved in session.")

    if uid:
        db.collection('users').document(uid).set(
            {'driveCredentials': creds_dict},
            merge=True
        )
        current_app.logger.debug("Drive credentials persisted to Firestore for uid=%s", uid)
    else:
        current_app.logger.warning(
            "No uid in OAuth state — Drive credentials not persisted to Firestore. "
            "Ensure the dashboard passes ?uid=<firebase_uid> when initiating /auth/google."
        )

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
