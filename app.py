import os
from flask import Flask
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from static_routes import static_bp
# … other blueprints …

def create_app():
    app = Flask(
        __name__,
        static_folder='../frontend',
        template_folder='../frontend'
    )

    # base config
    app.config.from_object(Config)

    # override SECRET_KEY
    app.config['SECRET_KEY'] = os.environ.get(
        'FLASK_SECRET_KEY',
        'dev-secret-guestmic'
    )

    # allow cross-site session cookies
    app.config['SESSION_COOKIE_SAMESITE'] = 'None'
    app.config['SESSION_COOKIE_SECURE']   = True
    # app.config['SESSION_COOKIE_DOMAIN']  = 'guestmic.onrender.com'

    # trust Render proxy headers (optional)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    # CORS + credentials
    CORS(
        app,
        supports_credentials=True,
        origins=["https://guestmic.web.app"]
    )

    # register all your blueprints
    app.register_blueprint(static_bp)
    # … etc …

    return app

# export for WSGI
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

