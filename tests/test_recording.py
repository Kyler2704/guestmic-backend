"""
Tests for the chunked recording pipeline endpoints.
All Firebase/Firestore/Storage interactions are mocked via conftest.py.
"""
import io
import json
from unittest.mock import MagicMock, patch


# ── Helpers ────────────────────────────────────────────────────────────────

def _link_doc(owner='uid-123'):
    """Fake Firestore doc for a valid guestLinks entry."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {'owner': owner}
    return doc


def _missing_doc():
    """Fake Firestore doc that does not exist."""
    doc = MagicMock()
    doc.exists = False
    return doc


def _session_doc(slug='my-show', owner='uid-123', guest='Alex'):
    """Fake Firestore doc for an existing recording session."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {'slug': slug, 'ownerUid': owner, 'guestName': guest}
    return doc


# ── /upload/session/start ──────────────────────────────────────────────────

def test_session_start_returns_session_id(client, mock_db):
    mock_db.collection.return_value.document.return_value.get.return_value = _link_doc()

    resp = client.post(
        '/upload/session/start',
        data=json.dumps({'slug': 'my-show', 'guestName': 'Alex'}),
        content_type='application/json',
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert 'sessionId' in body
    assert len(body['sessionId']) == 32  # uuid4().hex


def test_session_start_invalid_slug_returns_404(client, mock_db):
    mock_db.collection.return_value.document.return_value.get.return_value = _missing_doc()

    resp = client.post(
        '/upload/session/start',
        data=json.dumps({'slug': 'bad-slug', 'guestName': 'Alex'}),
        content_type='application/json',
    )

    assert resp.status_code == 404


def test_session_start_missing_slug_returns_400(client, mock_db):
    resp = client.post(
        '/upload/session/start',
        data=json.dumps({'guestName': 'Alex'}),
        content_type='application/json',
    )

    assert resp.status_code == 400


# ── /upload/chunk ──────────────────────────────────────────────────────────

def test_chunk_upload_stores_to_firebase(client, mock_db, mock_bucket):
    mock_db.collection.return_value.document.return_value.get.return_value = (
        _session_doc()
    )

    resp = client.post('/upload/chunk', data={
        'sessionId': 'abc123',
        'chunkIndex': '0',
        'audio': (io.BytesIO(b'fake-webm-bytes'), 'chunk.webm', 'audio/webm'),
    }, content_type='multipart/form-data')

    assert resp.status_code == 200
    assert resp.get_json()['success'] is True
    # Verify correct blob path was used
    mock_bucket.blob.assert_called_once_with(
        'recordings/my-show/abc123/chunk_000.webm'
    )
    mock_bucket.blob.return_value.upload_from_file.assert_called_once()


def test_chunk_upload_zero_pads_index(client, mock_db, mock_bucket):
    """chunkIndex=5 should produce chunk_005.webm, not chunk_5.webm."""
    mock_db.collection.return_value.document.return_value.get.return_value = (
        _session_doc()
    )

    client.post('/upload/chunk', data={
        'sessionId': 'abc123',
        'chunkIndex': '5',
        'audio': (io.BytesIO(b'x'), 'chunk.webm', 'audio/webm'),
    }, content_type='multipart/form-data')

    mock_bucket.blob.assert_called_once_with(
        'recordings/my-show/abc123/chunk_005.webm'
    )


def test_chunk_upload_missing_session_returns_404(client, mock_db):
    mock_db.collection.return_value.document.return_value.get.return_value = _missing_doc()

    resp = client.post('/upload/chunk', data={
        'sessionId': 'bad-id',
        'chunkIndex': '0',
        'audio': (io.BytesIO(b'x'), 'chunk.webm', 'audio/webm'),
    }, content_type='multipart/form-data')

    assert resp.status_code == 404


def test_chunk_upload_missing_fields_returns_400(client, mock_db):
    resp = client.post('/upload/chunk', data={
        'sessionId': 'abc123',
        # missing chunkIndex and audio
    }, content_type='multipart/form-data')

    assert resp.status_code == 400


# ── /upload/finalize ───────────────────────────────────────────────────────

def test_finalize_updates_firestore_and_spawns_thread(client, mock_db):
    mock_db.collection.return_value.document.return_value.get.return_value = (
        _session_doc()
    )

    with patch('recording.threading.Thread') as mock_thread:
        resp = client.post(
            '/upload/finalize',
            data=json.dumps({'sessionId': 'abc123', 'totalChunks': 3}),
            content_type='application/json',
        )

    assert resp.status_code == 200
    assert resp.get_json()['success'] is True

    # Verify Firestore updated with pending_merge status and expectedChunks
    update_call = mock_db.collection.return_value.document.return_value.update
    update_call.assert_called_once()
    update_args = update_call.call_args[0][0]
    assert update_args['status'] == 'pending_merge'
    assert update_args['expectedChunks'] == 3

    # Verify background thread was started
    mock_thread.return_value.start.assert_called_once()


def test_finalize_invalid_session_returns_404(client, mock_db):
    mock_db.collection.return_value.document.return_value.get.return_value = _missing_doc()

    resp = client.post(
        '/upload/finalize',
        data=json.dumps({'sessionId': 'bad', 'totalChunks': 1}),
        content_type='application/json',
    )

    assert resp.status_code == 404


def test_finalize_missing_fields_returns_400(client, mock_db):
    resp = client.post(
        '/upload/finalize',
        data=json.dumps({'sessionId': 'abc123'}),
        content_type='application/json',
    )

    assert resp.status_code == 400
