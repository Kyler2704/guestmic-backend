# backend/security.py
from flask import Blueprint, request, jsonify
from firebase_admin import auth as fb_auth, firestore
from datetime import datetime
from auth_helper.py import verify_token  # your existing helper
from your_db import db                     # your Firestore client

security_bp = Blueprint('security', __name__)

def log_security_event(uid: str, event: str):
    """Record a timestamped security event in Firestore."""
    db.collection('security_logs').add({
        'uid': uid,
        'event': event,
        'timestamp': firestore.SERVER_TIMESTAMP
    })

@security_bp.route('/api/security/password', methods=['POST'])
def change_password():
    uid = verify_token(request)
    if not uid:
        return jsonify({'error':'Unauthorized'}), 401

    data = request.get_json() or {}
    new_pw = data.get('new_password')
    if not new_pw or len(new_pw) < 6:
        return jsonify({'error':'Password must be at least 6 characters.'}), 400

    try:
        # Update via Firebase Admin SDK
        fb_auth.update_user(uid, password=new_pw)
        log_security_event(uid, 'password_changed')
        return jsonify({'success':True}), 200
    except Exception as e:
        return jsonify({'error':str(e)}), 500

@security_bp.route('/api/security/2fa', methods=['POST'])
def toggle_2fa():
    uid = verify_token(request)
    if not uid:
        return jsonify({'error':'Unauthorized'}), 401

    data = request.get_json() or {}
    enable = bool(data.get('enable', False))

    # Simply store a flag in Firestore
    db.collection('users').document(uid).set(
        {'two_factor_enabled': enable}, merge=True
    )
    log_security_event(uid, f'2fa_{"enabled" if enable else "disabled"}')
    return jsonify({'success':True, 'two_factor_enabled': enable}), 200

@security_bp.route('/api/security/activity', methods=['GET'])
def get_activity():
    uid = verify_token(request)
    if not uid:
        return jsonify({'error':'Unauthorized'}), 401

    # Pull the last 10 events
    snaps = (db.collection('security_logs')
               .where('uid','==',uid)
               .order_by('timestamp', direction=firestore.Query.DESCENDING)
               .limit(10)
               .stream())

    events = []
    for snap in snaps:
        data = snap.to_dict()
        ts = data.get('timestamp')
        # format timestamp to e.g. "YYYY-MM-DD HH:MM"
        ts_str = ts.to_datetime().strftime('%Y-%m-%d %H:%M') if ts else ''
        events.append({
            'date': ts_str,
            'event': data.get('event')
        })

    return jsonify(events), 200
