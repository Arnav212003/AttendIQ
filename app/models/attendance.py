from datetime import datetime, date, timezone

from app.extensions import db


class Attendance(db.Model):
    __tablename__ = "attendance"
    __table_args__ = (
        db.UniqueConstraint("date", "subject_id", "student_id", name="uq_attendance_day_subject_student"),
    )

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=lambda: date.today(), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    status = db.Column(db.String(10), nullable=False)  # "Present" / "Absent"
    mode = db.Column(db.String(30), default="Manual")  # Manual / Face Recognition / Voice Recognition
    marked_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    student = db.relationship("Student")

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "subject_id": self.subject_id,
            "student_id": self.student_id,
            "status": self.status,
            "mode": self.mode,
        }
