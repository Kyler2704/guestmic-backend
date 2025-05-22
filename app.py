import os
from flask import Flask
from flask_cors import CORS

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
    app = Flask(__name__, static_folder='../frontend', template_folder='../frontend')
    # Load core config (SECRET_KEY, session settings, max upload size)
    app.config.from_object(Config)
    CORS(app)

    # Register feature blueprints
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


if __name__ == '__main__':
    import os
    app = create_app()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)