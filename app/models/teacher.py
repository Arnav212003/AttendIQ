from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


class Teacher(db.Model):
    __tablename__ = "teachers"

    id = db.Column(db.Integer, primary_key=True)
    teacher_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    department = db.Column(db.String(120))
    role = db.Column(db.String(20), default="teacher", nullable=False)  # for RBAC
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    subjects = db.relationship("Subject", backref="teacher", lazy=True)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    def to_dict(self):
        return {
            "id": self.id,
            "teacher_name": self.teacher_name,
            "email": self.email,
            "department": self.department,
            "role": self.role,
        }
