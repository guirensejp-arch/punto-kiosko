import os

from dotenv import load_dotenv
from sqlalchemy.pool import StaticPool

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Configuración común a todos los entornos."""

    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///comanda.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Protección CSRF en todos los formularios POST (Flask-WTF).
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    # Archivo de branding editable por cliente (Día 0).
    BRANDING_FILE = os.path.join(BASE_DIR, 'branding.yaml')


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    """Entorno de tests: SQLite en memoria, CSRF desactivado."""

    TESTING = True
    DEBUG = False
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    SQLALCHEMY_ENGINE_OPTIONS = {
        'poolclass': StaticPool,
        'connect_args': {'check_same_thread': False},
    }


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}
