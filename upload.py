import io
from flask import Blueprint, request, session, jsonify, current_app
from auth_helper import get_drive_service
from googleapiclient.http import MediaIoBaseUpload

upload_bp = Blueprint('upload_bp', __name__)

@upload_bp.route('/upload/<slug>', methods=['POST'])
def upload_to_drive(slug):
    """
    Endpoint to receive a recorded audio blob and upload it to the host's Google Drive folder for this slug.
    """
    # 1) Check OAuth session
    if 'credentials' not in session:
        current_app.logger.warning("Unauthorized upload attempt; no OAuth credentials in session")
        return jsonify({'error': 'Unauthorized'}), 401

    # 2) Get uploaded file and optional name
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'No file provided'}), 400
    # Optional: a 'name' field from form
    name = request.form.get('name', slug)
    
    # 3) Initialize Drive API client
    creds = session['credentials']
    drive_service = get_drive_service(creds)

    # 4) Ensure there's a folder for this slug (create if needed)
    try:
        # Attempt to find an existing folder
        results = drive_service.files().list(
            q=f"mimeType='application/vnd.google-apps.folder' and name='{slug}' and trashed=false",
            spaces='drive',
            fields='files(id,name)'  
        ).execute()
        files = results.get('files', [])
        if files:
            folder_id = files[0]['id']
        else:
            # Create new folder
            metadata = {'name': slug, 'mimeType': 'application/vnd.google-apps.folder'}
            folder = drive_service.files().create(body=metadata, fields='id').execute()
            folder_id = folder.get('id')
    except Exception as e:
        current_app.logger.error(f"Error locating/creating folder: {e}")
        return jsonify({'error': 'Drive folder error'}), 500

    # 5) Upload the file into that folder
    try:
        media = MediaIoBaseUpload(file.stream, mimetype=file.mimetype, resumable=True)
        file_metadata = {
            'name': f"{name}.webm",
            'parents': [folder_id]
        }
        uploaded = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        link = uploaded.get('webViewLink')
        return jsonify({'link': link}), 200

    except Exception as e:
        current_app.logger.error(f"Drive upload error: {e}")
        return jsonify({'error': 'Upload failed'}), 500
