import uuid
import threading
import tempfile
import os
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, request, jsonify, current_app
from fb_admin import db, bucket, firestore
from google.cloud.firestore import Increment

logger = logging.getLogger(__name__)

recording_bp = Blueprint('recording_bp', __name__)


@recording_bp.route('/upload/session/start', methods=['POST'])
def session_start():
    """
    Create a new recording session in Firestore.
    Called by the guest recorder page when the guest clicks Start.
    """
    data = request.get_json() or {}
    slug = data.get('slug', '').strip()
    guest_name = data.get('guestName', 'Guest').strip()

    if not slug:
        return jsonify({'error': 'slug is required'}), 400

    # Verify slug exists and get the host's ownerUid
    link_doc = db.collection('guestLinks').document(slug).get()
    if not link_doc.exists:
        return jsonify({'error': 'Invalid link'}), 404

    owner_uid = link_doc.to_dict().get('owner')
    session_id = uuid.uuid4().hex

    db.collection('recordingSessions').document(session_id).set({
        'slug': slug,
        'ownerUid': owner_uid,
        'guestName': guest_name,
        'status': 'recording',
        'chunkCount': 0,
        'expectedChunks': None,
        'createdAt': firestore.SERVER_TIMESTAMP,
        'finalizedAt': None,
        'driveFileId': None,
    })

    return jsonify({'sessionId': session_id}), 200


@recording_bp.route('/upload/chunk', methods=['POST'])
def upload_chunk():
    """
    Receive one 2-minute audio chunk and write it to Firebase Storage.
    Called automatically by the browser every 2 minutes via MediaRecorder.ondataavailable.
    Recording continues in the browser while the upload happens in parallel.
    """
    session_id = request.form.get('sessionId', '').strip()
    chunk_index = request.form.get('chunkIndex', type=int)
    audio_file = request.files.get('audio')

    if not session_id or chunk_index is None or not audio_file:
        return jsonify({'error': 'Missing required fields'}), 400

    session_ref = db.collection('recordingSessions').document(session_id)
    session_doc = session_ref.get()
    if not session_doc.exists:
        return jsonify({'error': 'Invalid session'}), 404

    slug = session_doc.to_dict().get('slug')

    # Zero-padded chunk index ensures lexicographic sort == recording order
    blob_path = f'recordings/{slug}/{session_id}/chunk_{chunk_index:03d}.webm'
    blob = bucket.blob(blob_path)
    blob.upload_from_file(audio_file, content_type='audio/webm')

    # Atomically increment the chunk counter
    session_ref.update({'chunkCount': Increment(1)})

    return jsonify({'success': True}), 200


@recording_bp.route('/upload/finalize', methods=['POST'])
def finalize():
    """
    Called when the guest hits Stop. Marks the session as pending_merge and
    spawns a background thread that waits 3 minutes for any in-flight chunk
    uploads to land, then merges all chunks and uploads to the host's Drive.
    """
    data = request.get_json() or {}
    session_id = data.get('sessionId', '').strip()
    total_chunks = data.get('totalChunks')

    if not session_id or total_chunks is None:
        return jsonify({'error': 'Missing required fields'}), 400

    session_ref = db.collection('recordingSessions').document(session_id)
    session_doc = session_ref.get()
    if not session_doc.exists:
        return jsonify({'error': 'Invalid session'}), 404

    session_ref.update({
        'status': 'pending_merge',
        'expectedChunks': total_chunks,
        'finalizedAt': firestore.SERVER_TIMESTAMP,
    })

    # Spawn background thread — passes the app object so we can use app context
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_merge_and_upload,
        args=(app, session_id),
        daemon=True
    )
    thread.start()

    return jsonify({'success': True}), 200


def _merge_and_upload(app, session_id):
    """
    Background pipeline (not an HTTP route):
    1. Wait 3 minutes for any in-flight chunk uploads to complete
    2. Download all chunks from Firebase Storage in order
    3. Concatenate with pydub
    4. Upload merged file to the host's Google Drive
    5. Clean up chunks from Firebase Storage
    6. Update Firestore session status
    """
    with app.app_context():
        session_ref = db.collection('recordingSessions').document(session_id)

        try:
            session_data = session_ref.get().to_dict()
            expected_chunks = session_data.get('expectedChunks', 0)

            # Poll until all chunks have landed (or 2-min timeout) instead of blind sleep(180).
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                current = session_ref.get().to_dict().get('chunkCount', 0)
                if current >= expected_chunks:
                    break
                logger.info("Session %s: waiting for chunks (%d/%d) ...", session_id, current, expected_chunks)
                time.sleep(5)

            session_ref.update({'status': 'merging'})
            session_data = session_ref.get().to_dict()
            slug = session_data['slug']
            owner_uid = session_data['ownerUid']
            guest_name = session_data.get('guestName', 'Guest')

            with tempfile.TemporaryDirectory() as tmpdir:
                # Download all chunks in parallel
                chunk_paths = [None] * expected_chunks

                def _download_chunk(i):
                    blob_path = f'recordings/{slug}/{session_id}/chunk_{i:03d}.webm'
                    local_path = os.path.join(tmpdir, f'chunk_{i:03d}.webm')
                    try:
                        bucket.blob(blob_path).download_to_filename(local_path)
                        return i, local_path
                    except Exception:
                        logger.warning("Chunk %d missing for session %s — skipping", i, session_id)
                        return i, None

                with ThreadPoolExecutor(max_workers=min(expected_chunks or 1, 8)) as pool:
                    for i, path in pool.map(_download_chunk, range(expected_chunks)):
                        if path:
                            chunk_paths[i] = path

                chunk_paths = [p for p in chunk_paths if p is not None]

                if not chunk_paths:
                    raise RuntimeError("No chunks downloaded — nothing to merge")

                # MediaRecorder timeslice chunks are NOT independent WebM files.
                # Only chunk_000 carries the EBML header; subsequent chunks are
                # raw continuation segments. ffmpeg/pydub cannot open them
                # individually. The correct approach is to concatenate the raw
                # bytes in order — the result is a single valid WebM stream.
                merged_path = os.path.join(tmpdir, 'merged.webm')
                with open(merged_path, 'wb') as out:
                    for path in chunk_paths:
                        with open(path, 'rb') as chunk_file:
                            out.write(chunk_file.read())

                # Load host's Drive credentials from Firestore
                user_doc = db.collection('users').document(owner_uid).get()
                creds_data = (user_doc.to_dict() or {}).get('driveCredentials')
                if not creds_data:
                    raise RuntimeError(
                        f"No Drive credentials found for owner {owner_uid}. "
                        "Host must connect Google Drive before guests can record."
                    )

                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                from googleapiclient.http import MediaFileUpload

                creds = Credentials(
                    token=creds_data['token'],
                    refresh_token=creds_data['refresh_token'],
                    token_uri=creds_data['token_uri'],
                    client_id=creds_data['client_id'],
                    client_secret=creds_data['client_secret'],
                    scopes=creds_data['scopes'],
                )

                drive_service = build('drive', 'v3', credentials=creds, static_discovery=True)
                file_name = f'{guest_name}_{session_id}.webm'
                file_metadata = {'name': file_name}
                use_resumable = os.path.getsize(merged_path) > 5 * 1024 * 1024
                media = MediaFileUpload(merged_path, mimetype='audio/webm', resumable=use_resumable)
                result = drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                drive_file_id = result.get('id')

            # Clean up chunks from Firebase Storage
            for i in range(expected_chunks):
                blob_path = f'recordings/{slug}/{session_id}/chunk_{i:03d}.webm'
                try:
                    bucket.blob(blob_path).delete()
                except Exception:
                    logger.warning(
                        "Could not delete chunk %d for session %s", i, session_id
                    )

            session_ref.update({
                'status': 'complete',
                'driveFileId': drive_file_id,
            })
            logger.info(
                "Session %s merged and uploaded to Drive as file %s", session_id, drive_file_id
            )

        except Exception:
            logger.exception("Merge pipeline failed for session %s", session_id)
            session_ref.update({'status': 'error'})
