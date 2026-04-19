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

    session_data = session_doc.to_dict()
    slug = session_data.get('slug')
    owner_uid = session_data.get('ownerUid')

    # Zero-padded chunk index ensures lexicographic sort == recording order
    blob_path = f'recordings/{slug}/{session_id}/chunk_{chunk_index:03d}.webm'
    blob = bucket.blob(blob_path)
    blob.upload_from_file(audio_file, content_type='audio/webm')

    # Atomically increment the chunk counter
    session_ref.update({'chunkCount': Increment(1)})

    # Proactively refresh the host's Drive access token on every chunk so it
    # stays warm for the merge. Runs in background to not slow the response.
    threading.Thread(
        target=_refresh_drive_token_if_needed,
        args=(owner_uid,),
        daemon=True,
    ).start()

    return jsonify({'success': True}), 200


def _refresh_drive_token_if_needed(owner_uid):
    try:
        from datetime import datetime
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        user_doc = db.collection('users').document(owner_uid).get()
        creds_data = (user_doc.to_dict() or {}).get('driveCredentials')
        if not creds_data:
            return

        expiry_str = creds_data.get('expiry')
        expiry = datetime.fromisoformat(expiry_str).replace(tzinfo=None) if expiry_str else None
        creds = Credentials(
            token=creds_data['token'],
            refresh_token=creds_data['refresh_token'],
            token_uri=creds_data['token_uri'],
            client_id=creds_data['client_id'],
            client_secret=creds_data['client_secret'],
            scopes=creds_data['scopes'],
            expiry=expiry,
        )
        if not creds.valid:
            creds.refresh(Request())
            db.collection('users').document(owner_uid).update({
                'driveCredentials.token': creds.token,
                'driveCredentials.expiry': creds.expiry.isoformat() if creds.expiry else None,
            })
            logger.info("Proactively refreshed Drive token for owner %s", owner_uid)
    except Exception:
        logger.warning("Background Drive token refresh failed for owner %s", owner_uid, exc_info=True)


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


def _park_merged_recording(session_id, slug, merged_path, session_ref, owner_uid):
    """
    Called when the Drive upload fails due to a revoked/expired refresh token.
    Saves the already-merged file to Firebase Storage so no recording data is lost,
    then marks the session as pending_drive_upload so the dashboard can retry
    after the host reconnects Drive.
    """
    try:
        parked_blob_path = f'recordings/{slug}/{session_id}/merged.webm'
        bucket.blob(parked_blob_path).upload_from_filename(merged_path, content_type='audio/webm')
        session_ref.update({
            'status': 'pending_drive_upload',
            'mergedBlobPath': parked_blob_path,
        })
        logger.info(
            "Session %s: Drive token revoked — merged recording parked at %s for later upload",
            session_id, parked_blob_path,
        )
    except Exception:
        logger.exception("Session %s: failed to park merged recording after Drive auth error", session_id)
        session_ref.update({'status': 'error'})


@recording_bp.route('/retry-drive-upload/<session_id>', methods=['POST'])
def retry_drive_upload(session_id):
    """
    Called from the dashboard after the host reconnects Google Drive.
    Downloads the parked merged file from Firebase Storage and uploads it to Drive.
    """
    from auth_helper import verify_token
    uid = verify_token(request)
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    session_ref = db.collection('recordingSessions').document(session_id)
    session_data = session_ref.get().to_dict()
    if not session_data or session_data.get('status') != 'pending_drive_upload':
        return jsonify({'error': 'Session not pending Drive upload'}), 400
    if session_data.get('ownerUid') != uid:
        return jsonify({'error': 'Forbidden'}), 403

    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_retry_drive_upload_bg,
        args=(app, session_id),
        daemon=True,
    )
    thread.start()
    return jsonify({'success': True}), 200


def _retry_drive_upload_bg(app, session_id):
    with app.app_context():
        session_ref = db.collection('recordingSessions').document(session_id)
        try:
            session_data = session_ref.get().to_dict()
            owner_uid = session_data['ownerUid']
            guest_name = session_data.get('guestName', 'Guest')
            merged_blob_path = session_data['mergedBlobPath']

            user_doc = db.collection('users').document(owner_uid).get()
            creds_data = (user_doc.to_dict() or {}).get('driveCredentials')
            if not creds_data:
                logger.error("Session %s retry: no Drive credentials for owner %s", session_id, owner_uid)
                session_ref.update({'status': 'error'})
                return

            from datetime import datetime
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            expiry_str = creds_data.get('expiry')
            expiry = datetime.fromisoformat(expiry_str).replace(tzinfo=None) if expiry_str else None
            creds = Credentials(
                token=creds_data['token'],
                refresh_token=creds_data['refresh_token'],
                token_uri=creds_data['token_uri'],
                client_id=creds_data['client_id'],
                client_secret=creds_data['client_secret'],
                scopes=creds_data['scopes'],
                expiry=expiry,
            )
            if not creds.valid:
                creds.refresh(Request())
                db.collection('users').document(owner_uid).update({
                    'driveCredentials.token': creds.token,
                    'driveCredentials.expiry': creds.expiry.isoformat() if creds.expiry else None,
                })

            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as tmp:
                merged_path = tmp.name
            try:
                bucket.blob(merged_blob_path).download_to_filename(merged_path)

                drive_service = build('drive', 'v3', credentials=creds, static_discovery=True)
                file_name = f'{guest_name}_{session_id}.webm'
                use_resumable = os.path.getsize(merged_path) > 5 * 1024 * 1024
                media = MediaFileUpload(merged_path, mimetype='audio/webm', resumable=use_resumable)
                result = drive_service.files().create(
                    body={'name': file_name},
                    media_body=media,
                    fields='id',
                ).execute()
                drive_file_id = result.get('id')
            finally:
                os.unlink(merged_path)

            bucket.blob(merged_blob_path).delete()
            session_ref.update({'status': 'complete', 'driveFileId': drive_file_id})
            logger.info("Session %s retry: uploaded to Drive as %s", session_id, drive_file_id)

        except Exception:
            logger.exception("Session %s retry Drive upload failed", session_id)
            session_ref.update({'status': 'error'})


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

                from datetime import datetime
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request
                from googleapiclient.discovery import build
                from googleapiclient.http import MediaFileUpload

                expiry_str = creds_data.get('expiry')
                expiry = datetime.fromisoformat(expiry_str).replace(tzinfo=None) if expiry_str else None

                creds = Credentials(
                    token=creds_data['token'],
                    refresh_token=creds_data['refresh_token'],
                    token_uri=creds_data['token_uri'],
                    client_id=creds_data['client_id'],
                    client_secret=creds_data['client_secret'],
                    scopes=creds_data['scopes'],
                    expiry=expiry,
                )

                from google.auth.exceptions import RefreshError as _RefreshError

                if not creds.valid:
                    try:
                        creds.refresh(Request())
                        logger.info("Session %s: Drive token refreshed", session_id)
                        db.collection('users').document(owner_uid).update({
                            'driveCredentials.token': creds.token,
                            'driveCredentials.expiry': creds.expiry.isoformat() if creds.expiry else None,
                        })
                    except _RefreshError:
                        _park_merged_recording(session_id, slug, merged_path, session_ref, owner_uid)
                        return

                try:
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
                except _RefreshError:
                    # Token expired mid-upload (long recordings exceed the 1hr access token TTL)
                    _park_merged_recording(session_id, slug, merged_path, session_ref, owner_uid)
                    return

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
