# config.py
import os
import datetime

class Config:
    # Configuración de JWT
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'super-secreto-y-dificil-de-adivinar-manizales-caps')
    JWT_ACCESS_TOKEN_EXPIRES = datetime.timedelta(minutes=60)

    # Configuración de la base de datos MySQL (¡ASEGÚRATE DE USAR TUS CREDENCIALES REALES!)
    DB_USER = os.environ.get('DB_USER', 'root') # Reemplaza 'tu_usuario_mysql'
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'admin') # Reemplaza 'tu_contrasena_mysql'
    DB_HOST = os.environ.get('DB_HOST', 'localhost:3306')
    DB_NAME = os.environ.get('DB_NAME', 'capsmanizales_est_aps')

    SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configuración de compresión
    COMPRESS_MIMETYPES = [
        'text/html',
        'text/css',
        'text/xml',
        'text/plain',
        'application/json',
        'application/javascript',
        'application/xml+rss',
        'application/atom+xml',
        'image/svg+xml'
    ]
    COMPRESS_LEVEL = 6  # Nivel de compresión (1-9, 6 es un buen balance)
    COMPRESS_MIN_SIZE = 500  # Solo comprimir respuestas > 500 bytes
    COMPRESS_ALGORITHM = ['br', 'gzip', 'deflate']  # Prioridad: Brotli, luego gzip, luego deflate