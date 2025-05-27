import re
from flask import Blueprint, request, jsonify
from fb_admin import firestore
from auth_helper import verify_token
from fb_admin import db
from flask import current_app

links_bp = Blueprint('links_bp', __name__)

@links_bp.route('/generate-link', methods=['POST'])
def generate_link():
    current_app.logger.debug(f"Session contents on generate-link: {dict(session)}")
    if 'credentials' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

def generate_link_route():
    uid = verify_token(request)
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json() or {}
    slug = data.get('slug','').strip()
    # allow only letters, numbers and hyphens; 3–30 chars
    if not re.fullmatch(r'[A-Za-z0-9\-]{3,30}', slug):
        return jsonify({'error': 'Slug must be 3-30 chars, alphanumeric or hyphens.'}), 400
    doc_ref = db.collection('guestLinks').document(slug)
    if doc_ref.get().exists:
        return jsonify({'error': 'Slug exists.'}), 409
    doc_ref.set({'slug': slug, 'owner': uid, 'createdAt': firestore.SERVER_TIMESTAMP})
    return jsonify({'url': f'/guest/{slug}'}), 200

links_bp.add_url_rule('/generate-link', view_func=generate_link_route, methods=['POST'])
