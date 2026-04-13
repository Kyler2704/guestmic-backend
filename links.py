import re
import traceback
from flask import Blueprint, request, jsonify, current_app, url_for
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
        # Verify Firebase token — this is the sole auth gate.
        # We no longer require session['credentials'] here because the session
        # cookie is not reliably forwarded on cross-origin requests from the
        # Firebase-hosted frontend. Drive credentials are stored in Firestore
        # (keyed by uid) and retrieved by the merge pipeline when needed.
        uid = verify_token(request)
        if not uid:
            current_app.logger.warning("Unauthorized generate-link attempt; invalid Firebase token")
            return jsonify({'error': 'Unauthorized'}), 401

        # Ensure the user has connected Google Drive before allowing link creation
        user_doc = db.collection('users').document(uid).get()
        if not user_doc.exists or not (user_doc.to_dict() or {}).get('driveCredentials'):
            current_app.logger.warning("generate-link blocked; user %s has not connected Drive", uid)
            return jsonify({'error': 'Please connect Google Drive before generating a link.'}), 403

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
