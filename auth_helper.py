from flask import request
from fb_admin import firebase_auth as fb_auth

# Verify Firebase ID token and return uid or None

def verify_token(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    id_token = auth_header.split(' ')[1]
    try:
        decoded = fb_auth.verify_id_token(id_token)
        return decoded['uid']
    except Exception:
        return None