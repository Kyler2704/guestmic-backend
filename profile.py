from flask import Blueprint, request, jsonify
from datetime import timedelta
from auth_helper import verify_token
from fb_admin import firestore
from fb_admin import fb_storage
from auth_helper import verify_token
from fb_admin import db, bucket


profile_bp = Blueprint('profile_bp', __name__)

@profile_bp.route('/api/profile', methods=['GET', 'POST'])
def profile():
    uid = verify_token(request)
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401
    doc_ref = db.collection('users').document(uid)
    if request.method == 'GET':
        doc = doc_ref.get()
        return jsonify(doc.to_dict() or {}), 200
    data = request.get_json() or {}
    update_data = {k: v for k, v in data.items() if k in ('firstName','lastName','username')}
    if update_data:
        doc_ref.set(update_data, merge=True)
    return jsonify({'success': True}), 200

@profile_bp.route('/api/profile/avatar', methods=['POST'])
def upload_avatar():
    uid = verify_token(request)
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401
    if 'avatar' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['avatar']
    blob = bucket.blob(f'avatars/{uid}')
    blob.upload_from_file(file, content_type=file.content_type)
    url = blob.generate_signed_url(expiration=timedelta(days=3650))
    db.collection('users').document(uid).set({'avatarUrl': url}, merge=True)
    return jsonify({'avatarUrl': url}), 200