import os
from flask import Flask
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from static_routes import static_bp
from oauth import oauth_bp
from links import links_bp
from profile import profile_bp
from guest import guest_bp
from upload import upload_bp
from errors import errors_bp
from security import security_bp
from email_notifications import notifications_bp


def create_app():
    # Initialize Flask app with static and template folders
    app = Flask(
        __name__,
        static_folder='../frontend',
        template_folder='../frontend'
    )

    # Load base configuration
    app.config.from_object(Config)

    # Override SECRET_KEY for sessions, using env var or dev fallback
    app.config['SECRET_KEY'] = os.environ.get(
        'FLASK_SECRET_KEY',
        'dev-secret-guestmic'
    )

    # Configure session cookies to work across domains
    app.config['SESSION_COOKIE_SAMESITE'] = 'None'
    app.config['SESSION_COOKIE_SECURE'] = True
    # Uncomment and set if needed:
    # app.config['SESSION_COOKIE_DOMAIN'] = 'guestmic-backend.onrender.com'

    # Trust proxy headers from Render's HTTPS termination
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    # Enable CORS with credentials from your front-end origin
    CORS(
        app,
        supports_credentials=True,
        origins=["https://guestmic.web.app"]
    )

    # Register blueprints
    app.register_blueprint(static_bp)
    app.register_blueprint(oauth_bp)
    app.register_blueprint(links_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(guest_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(errors_bp)
    app.register_blueprint(security_bp)
    app.register_blueprint(notifications_bp)

    return app


# Expose the app for WSGI
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)



