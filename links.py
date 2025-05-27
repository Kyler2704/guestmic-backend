import re
import traceback
from flask import Blueprint, request, session, jsonify, current_app, url_for
from auth_helper import verify_token
from fb_admin import firestore, db

# Blueprint for link-generation
links_bp = Blueprint('links_bp', __name__)

@links_bp.route('/generate-link', methods=['POST'])
def generate_link():
    """
    Creates a guest link for recording. Expects JSON { slug: string }.
    Requires valid Google OAuth session and valid Firebase token.
    """
    try:
        # Debug: inspect session and incoming request
        current_app.logger.debug(f"Session contents on generate-link: {dict(session)}")
        current_app.logger.debug(f"Request JSON: {request.get_data()}")

        # Ensure OAuth credentials
        if 'credentials' not in session:
            current_app.logger.warning("Unauthorized generate-link attempt; no OAuth credentials in session")
            return jsonify({'error': 'Unauthorized'}), 401

        # Verify Firebase token
        uid = verify_token(request)
        if not uid:
            current_app.logger.warning("Unauthorized generate-link attempt; invalid Firebase token")
            return jsonify({'error': 'Unauthorized'}), 401

        # Parse and validate slug
        data = request.get_json(force=True)
        slug = data.get('slug', '').strip()
        if not re.fullmatch(r'[A-Za-z0-9\-]{3,30}', slug):
            current_app.logger.warning(f"Invalid slug provided: {slug}")
            return jsonify({'error': 'Slug must be 3-30 chars, alphanumeric or hyphens.'}), 400

        # Check slug uniqueness in Firestore
        doc_ref = db.collection('guestLinks').document(slug)
        if doc_ref.get().exists:
            current_app.logger.warning(f"Slug already exists: {slug}")
            return jsonify({'error': 'Slug exists.'}), 409

        # Store slug ownership
        doc_ref.set({'slug': slug, 'owner': uid, 'createdAt': firestore.SERVER_TIMESTAMP})

        # Generate relative guest URL
        guest_url = url_for('guest_bp.serve_guest', slug=slug, _external=False)
        current_app.logger.info(f"Generated guest link: {guest_url} for user {uid}")
        return jsonify({'url': guest_url}), 200

    except Exception as e:
        current_app.logger.error(f"Error in generate-link: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Internal server error'}), 500
