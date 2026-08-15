from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    roll_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    class_section = db.Column(db.String(50))
    email_phone = db.Column(db.String(120))
    # Hashed 4-digit PIN, required alongside roll_number for self-service
    # endpoints (viewing own subjects/attendance, joining a subject) - stored
    # hashed so it isn't recoverable in plaintext from a DB dump.
    pin_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    enrollments = db.relationship("Enrollment", backref="student", lazy=True, cascade="all, delete-orphan")
    face_embeddings = db.relationship("FaceEmbedding", backref="student", lazy=True, cascade="all, delete-orphan")
    voice_embeddings = db.relationship("VoiceEmbedding", backref="student", lazy=True, cascade="all, delete-orphan")

    def set_pin(self, raw_pin):
        self.pin_hash = generate_password_hash(raw_pin)

    def check_pin(self, raw_pin):
        return check_password_hash(self.pin_hash, raw_pin or "")

    def to_dict(self, include_pin=None):
        data = {
            "id": self.id,
            "name": self.name,
            "roll_number": self.roll_number,
            "class_section": self.class_section,
            "email_phone": self.email_phone,
        }
        if include_pin:
            data["pin_code"] = include_pin  # plaintext PIN passed in explicitly, once, at creation time
        return data
