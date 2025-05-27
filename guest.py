from flask import Blueprint, render_template

guest_bp = Blueprint('guest_bp', __name__)


@guest_bp.route('/<slug>')
def serve_guest(slug):
    """Render the guest recorder page with the passed slug."""
    return render_template('GuestMicrecord.html', slug=slug)
