import io
from flask import Blueprint, request, session, jsonify, current_app
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

upload_bp = Blueprint('upload_bp', __name__)

@upload_bp.route('/upload/<slug>', methods=['POST'])
def upload_to_drive(slug):
    """
    Endpoint to receive a recorded audio blob and upload it to the host's Google Drive folder for this slug.
    """
    # 1) Check OAuth session
    creds_data = session.get('credentials')
    if not creds_data:
        current_app.logger.warning("Unauthorized upload attempt; no OAuth credentials in session")
        return jsonify({'error': 'Unauthorized'}), 401

    # 2) Build Credentials object
    creds = Credentials(
        token=creds_data['token'],
        refresh_token=creds_data.get('refresh_token'),
        token_uri=creds_data['token_uri'],
        client_id=creds_data['client_id'],
        client_secret=creds_data['client_secret'],
        scopes=creds_data['scopes']
    )
    drive_service = build('drive', 'v3', credentials=creds)

    # 3) Get uploaded file and optional name
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'No file provided'}), 400
    name = request.form.get('name', slug)

    # 4) Ensure folder exists
    try:
        query = f"mimeType='application/vnd.google-apps.folder' and name='{slug}' and trashed=false"
        results = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id,name)'
        ).execute()
        items = results.get('files', [])
        if items:
            folder_id = items[0]['id']
        else:
            folder_meta = {'name': slug, 'mimeType': 'application/vnd.google-apps.folder'}
            folder = drive_service.files().create(body=folder_meta, fields='id').execute()
            folder_id = folder['id']
    except Exception as e:
        current_app.logger.error(f"Error locating/creating folder: {e}")
        return jsonify({'error': 'Drive folder error'}), 500

    # 5) Upload file into folder
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
