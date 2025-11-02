# app/__init__.py
from flask import Flask
from flask_compress import Compress
from app.config import Config
from app.models import db, jwt

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Inicializar extensiones con la instancia de la aplicación
    db.init_app(app)
    jwt.init_app(app)
    
    # Configurar compresión con Brotli
    compress = Compress()
    compress.init_app(app)

    # Registrar Blueprints
    from app.auth.routes import auth_bp
    app.register_blueprint(auth_bp)

    from app.sync.routes import sync_bp
    app.register_blueprint(sync_bp)

    # Asegurarse de crear las tablas si la base de datos está vacía (solo para desarrollo)
    # with app.app_context():
    #     db.create_all() # ¡Solo para desarrollo! No uses esto en producción con una DB existente

    return app