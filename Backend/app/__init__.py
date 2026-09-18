from flask import Flask
from flask_cors import CORS
from config import Config

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Enable CORS for all routes (allows ASP.NET frontend to call this API)
    CORS(app)

    # Register routes
    from app.routes import bp as main_bp
    app.register_blueprint(main_bp)

    return app