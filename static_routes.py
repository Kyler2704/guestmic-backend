from flask import Blueprint, send_from_directory, current_app

static_bp = Blueprint('static_bp', __name__)  # no module-level static folder lookup

@static_bp.route('/')
def home():
    """Serve the main homepage."""
    return send_from_directory(
        current_app.static_folder,          # safe to use here
        'GuestMicHomepage.html',
    )

@static_bp.route('/login')
def login_page():
    """Serve the login page."""
    return send_from_directory(
        current_app.static_folder,
        'GuestMicLogin.html',
    )

@static_bp.route('/signup')
def signup_page():
    """Serve the signup page."""
    return send_from_directory(
        current_app.static_folder,
        'GuestMicSignup.html',
    )

@static_bp.route('/dashboard')
def dashboard():
    """Serve the dashboard."""
    return send_from_directory(
        current_app.static_folder,
        'GuestMicDashboard.html',
    )

@static_bp.route('/dashboard/account')
def account():
    """Serve the account settings page."""
    return send_from_directory(
        current_app.static_folder,
        'GuestMicAccount.html',
    )

@static_bp.route('/<path:filename>')
def serve_frontend(filename):
    """Serve all other frontend assets (CSS, JS, images, etc.)."""
    return send_from_directory(
        current_app.static_folder,
        filename,
    )