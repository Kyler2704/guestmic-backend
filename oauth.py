from flask import Blueprint, session, redirect, request, jsonify, current_app
from google_auth_oauthlib.flow import Flow
from config import Config

oauth_bp = Blueprint('oauth_bp', __name__, url_prefix='/auth/google')

SCOPES               = Config.SCOPES
CLIENT_SECRETS_FILE  = Config.CLIENT_SECRETS_FILE
# Note: this must exactly match the route below!
REDIRECT_URI         = Config.REDIRECT_URI  # e.g. "https://guestmic.onrender.com/auth/google/callback"

@oauth_bp.route('', methods=['GET'])
def login_oauth():
    """
    Step 1: redirect user to Google's consent screen.
    """
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    auth_url, state = flow.authorization_url(
        prompt='consent',
        include_granted_scopes=True
    )

    # keep the state in-session so we can verify on callback
    session.permanent = True
    session['state'] = state

    current_app.logger.debug(f"Generated OAuth state: {state}")
    return redirect(auth_url)


@oauth_bp.route('/callback', methods=['GET'])
def oauth2callback():
    """
    Step 2: Google redirects back here with ?state=…&code=…
    """
    incoming_state = request.args.get('state')
    saved_state    = session.get('state')

    # 1) verify we still have the original state in our session
    if not saved_state or incoming_state != saved_state:
        current_app.logger.warning(
            f"State mismatch: incoming={incoming_state} saved={saved_state}"
        )
        return "Session expired or invalid. Please try again.", 400

    # 2) finish the OAuth flow
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=saved_state,
        redirect_uri=REDIRECT_URI
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

    # clean up
    session.pop('state', None)

    return redirect('/dashboard')


@oauth_bp.route('/drive-status', methods=['GET'])
def drive_status():
    return jsonify({'connected': 'credentials' in session})
