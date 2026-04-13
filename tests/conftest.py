import sys
from unittest.mock import MagicMock
import pytest

# --- Build a fake fb_admin module before any app code imports it ---
_mock_db = MagicMock()
_mock_bucket = MagicMock()
_mock_firebase_auth = MagicMock()
_mock_firestore = MagicMock()
_mock_firestore.SERVER_TIMESTAMP = 'SERVER_TIMESTAMP'

_fb_admin_mock = MagicMock()
_fb_admin_mock.db = _mock_db
_fb_admin_mock.bucket = _mock_bucket
_fb_admin_mock.firebase_auth = _mock_firebase_auth
_fb_admin_mock.firestore = _mock_firestore

sys.modules.setdefault('fb_admin', _fb_admin_mock)
sys.modules.setdefault('firebase_admin', MagicMock())
sys.modules.setdefault('firebase_admin.credentials', MagicMock())
sys.modules.setdefault('firebase_admin.firestore', MagicMock())
sys.modules.setdefault('firebase_admin.storage', MagicMock())
sys.modules.setdefault('firebase_admin.auth', MagicMock())
sys.modules.setdefault('google.cloud.firestore', MagicMock())
sys.modules.setdefault('google.oauth2.credentials', MagicMock())
sys.modules.setdefault('googleapiclient.discovery', MagicMock())
sys.modules.setdefault('googleapiclient.http', MagicMock())
sys.modules.setdefault('pydub', MagicMock())


@pytest.fixture(autouse=True)
def reset_mocks():
    _mock_db.reset_mock()
    _mock_bucket.reset_mock()
    _mock_firebase_auth.reset_mock()
    yield


@pytest.fixture
def app():
    import importlib
    import app as app_module
    importlib.reload(app_module)
    flask_app = app_module.create_app()
    flask_app.config['TESTING'] = True
    flask_app.config['SECRET_KEY'] = 'test-secret'
    flask_app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mock_db():
    return _mock_db


@pytest.fixture
def mock_bucket():
    return _mock_bucket
