import os
from flask import Blueprint, request, jsonify, session
from werkzeug.utils import secure_filename
from datetime import datetime

ALLOWED_MIMETYPES = {
    'audio/webm': '.webm',
    'audio/wav': '.wav',
}

upload_bp = Blueprint('upload_bp', __name__)


@upload_bp.route('/upload', methods=['POST'])
def upload_audio():
    """Handle guest audio uploads, save locally, and return metadata."""
    if 'credentials' not in session:
        return 'Not authenticated', 401

    guest_name = request.form.get('name', 'Guest').strip().replace(' ', '_')
    file = request.files.get('audio')
    if not file:
        return jsonify({'error': 'No audio provided.'}), 400

    ext = ALLOWED_MIMETYPES.get(file.mimetype)
    if not ext:
        return jsonify({'error': 'Unsupported file type.'}), 400

    ts = datetime.now().strftime('%Y-%m-%d_%I-%M%p')
    safe_name = secure_filename(guest_name)
    fname = f"{safe_name}_{ts}{ext}"
    os.makedirs('temp_audio', exist_ok=True)
    path = os.path.join('temp_audio', secure_filename(fname))
    file.save(path)

    # TODO: implement upload-to-Drive using stored OAuth2 credentials

    return jsonify({'success': True, 'file': fname}), 200