import os
from datetime import timedelta


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change-this-jwt-secret")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Uploaded face / voice files
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    FACE_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "faces")
    VOICE_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "voices")
    FACE_MODEL_PATH = os.path.join(UPLOAD_FOLDER, "face_model.yml")

    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB uploads

    # Celery / Redis (for async face-model retraining)
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

    # Rate limiting storage - defaults to in-memory; override with redis:// in production
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    # Falls back to SQLite for easy local dev; override with DATABASE_URL for Postgres
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'dev.db')}"
    )


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    RATELIMIT_STORAGE_URI = "memory://"


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg2://attendance_user:attendance_pass@localhost:5432/attendance_db"
    )
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "redis://localhost:6379/1")


config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
