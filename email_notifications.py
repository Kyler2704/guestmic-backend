# backend/email_notifications.py
from flask import Blueprint, request, jsonify
from firebase_admin import auth as fb_auth
from your_auth_helper import verify_token     # your existing token verifier
from your_db import db                         # your Firestore client

notifications_bp = Blueprint('notifications', __name__)

@notifications_bp.route('/api/user/email', methods=['GET', 'POST'])
def manage_email():
    uid = verify_token(request)
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    user_ref = db.collection('users').document(uid)

    if request.method == 'GET':
        # Fetch primary from Auth and secondary from Firestore
        try:
            fb_user = fb_auth.get_user(uid)
            secondary = user_ref.get().to_dict().get('secondaryEmail', '')
            return jsonify({
                'primaryEmail': fb_user.email,
                'secondaryEmail': secondary
            }), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # POST: update primary or secondary
    data = request.get_json() or {}
    new_primary = data.get('primaryEmail')
    new_secondary = data.get('secondaryEmail')

    result = {}
    # update primary via Admin SDK
    if new_primary:
        try:
            fb_auth.update_user(uid, email=new_primary)
            result['primaryEmail'] = new_primary
        except Exception as e:
            return jsonify({'error': f'Primary update failed: {e}'}), 400

    # update secondary in Firestore
    if new_secondary is not None:
        user_ref.set({'secondaryEmail': new_secondary}, merge=True)
        result['secondaryEmail'] = new_secondary

    return jsonify({'success': True, **result}), 200


@notifications_bp.route('/api/user/notifications/email', methods=['GET', 'POST'])
def email_prefs():
    uid = verify_token(request)
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    user_ref = db.collection('users').document(uid)

    if request.method == 'GET':
        prefs = user_ref.get().to_dict().get('emailNotifications', {})
        return jsonify(prefs), 200

    # POST: expects a JSON of boolean prefs
    prefs = request.get_json() or {}
    user_ref.set({'emailNotifications': prefs}, merge=True)
    return jsonify({'success': True, 'emailNotifications': prefs}), 200


@notifications_bp.route('/api/user/notifications/dashboard', methods=['GET', 'POST'])
def dashboard_prefs():
    uid = verify_token(request)
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    user_ref = db.collection('users').document(uid)

    if request.method == 'GET':
        prefs = user_ref.get().to_dict().get('dashboardNotifications', {})
        return jsonify(prefs), 200

    prefs = request.get_json() or {}
    user_ref.set({'dashboardNotifications': prefs}, merge=True)
    return jsonify({'success': True, 'dashboardNotifications': prefs}), 200
