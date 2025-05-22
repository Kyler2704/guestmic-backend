import json
import logging
from flask import Blueprint, jsonify
from werkzeug.exceptions import HTTPException

errors_bp = Blueprint('errors_bp', __name__)
logger = logging.getLogger(__name__)


@errors_bp.app_errorhandler(HTTPException)
def handle_http_exception(e):
    """Return JSON for all HTTP errors."""
    response = e.get_response()
    response.data = json.dumps({'error': e.description})
    response.content_type = 'application/json'
    return response, e.code


@errors_bp.app_errorhandler(Exception)
def handle_unexpected_error(e):
    """Log unexpected exceptions and return 500."""
    logger.exception("Unhandled exception:")
    return jsonify({'error': 'Internal server error.'}), 500