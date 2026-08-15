from datetime import datetime, timezone

from app.extensions import db


class Subject(db.Model):
    __tablename__ = "subjects"

    id = db.Column(db.Integer, primary_key=True)
    subject_name = db.Column(db.String(120), nullable=False)
    subject_code = db.Column(db.String(10), unique=True, nullable=False, index=True)
    section = db.Column(db.String(50))
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    enrollments = db.relationship("Enrollment", backref="subject", lazy=True, cascade="all, delete-orphan")
    attendance_records = db.relationship("Attendance", backref="subject", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "subject_name": self.subject_name,
            "subject_code": self.subject_code,
            "section": self.section,
            "teacher_id": self.teacher_id,
        }
