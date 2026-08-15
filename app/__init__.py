import os

from flask import Flask

from app.config import config_map
from app.extensions import db, migrate, jwt, limiter


def create_app(env=None):
    app = Flask(__name__)

    env = env or os.environ.get("FLASK_ENV", "development")
    app.config.from_object(config_map.get(env, config_map["default"]))

    # ensure upload dirs exist
    os.makedirs(app.config["FACE_UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["VOICE_UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)

    from app.models import Teacher, Student, Subject, Enrollment, Attendance, FaceEmbedding, VoiceEmbedding  # noqa: F401

    from app.routes.auth_routes import auth_bp
    from app.routes.student_routes import student_bp
    from app.routes.teacher_routes import teacher_bp
    from app.routes.subject_routes import subject_bp
    from app.routes.attendance_routes import attendance_bp
    from app.routes.face_routes import face_bp
    from app.routes.voice_routes import voice_bp
    from app.routes.web_routes import web_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(student_bp, url_prefix="/api/students")
    app.register_blueprint(teacher_bp, url_prefix="/api/teachers")
    app.register_blueprint(subject_bp, url_prefix="/api/subjects")
    app.register_blueprint(attendance_bp, url_prefix="/api/attendance")
    app.register_blueprint(face_bp, url_prefix="/api/face")
    app.register_blueprint(voice_bp, url_prefix="/api/voice")
    app.register_blueprint(web_bp)

    @app.get("/api/health")
    def health_check():
        return {"status": "ok"}

    register_error_handlers(app)

    return app


def register_error_handlers(app):
    from flask import jsonify
    from werkzeug.exceptions import HTTPException

    @app.errorhandler(HTTPException)
    def handle_http_exception(err):
        return jsonify({"success": False, "message": err.description}), err.code

    @app.errorhandler(Exception)
    def handle_unexpected_exception(err):
        app.logger.exception("Unhandled exception")
        return jsonify({"success": False, "message": "Internal server error."}), 500

    @app.errorhandler(422)
    @app.errorhandler(400)
    def handle_validation_error(err):
        return jsonify({"success": False, "message": str(err)}), 400
