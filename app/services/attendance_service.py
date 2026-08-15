from datetime import date

from app.extensions import db
from app.models.attendance import Attendance
from app.models.student import Student
from app.models.subject import Subject


def save_attendance(subject_id, attendance_data, attendance_mode="Manual"):
    subject = Subject.query.get(subject_id)

    if subject is None:
        return False, "Subject not found."

    today = date.today()
    updated_count = 0
    created_count = 0

    for entry in attendance_data:
        record = Attendance.query.filter_by(
            date=today, subject_id=subject_id, student_id=entry["student_id"]
        ).first()

        if record:
            record.status = entry["status"]
            record.mode = attendance_mode
            updated_count += 1
        else:
            db.session.add(
                Attendance(
                    date=today,
                    subject_id=subject_id,
                    student_id=entry["student_id"],
                    status=entry["status"],
                    mode=attendance_mode,
                )
            )
            created_count += 1

    db.session.commit()

    if updated_count and created_count:
        return True, "Attendance saved. Existing records updated and new records added."
    if updated_count:
        return True, "Attendance updated successfully."
    return True, "Attendance saved successfully."


def save_manual_attendance(subject_id, attendance_data):
    return save_attendance(subject_id, attendance_data, attendance_mode="Manual")


def filter_attendance(subject_id=None, attendance_date=None, teacher_id=None):
    query = Attendance.query

    if subject_id:
        query = query.filter_by(subject_id=subject_id)
    elif teacher_id is not None:
        # No specific subject requested - restrict to this teacher's own subjects
        # only, never leak attendance across teachers.
        query = query.join(Subject, Attendance.subject_id == Subject.id).filter(
            Subject.teacher_id == teacher_id
        )

    if attendance_date:
        query = query.filter_by(date=attendance_date)

    return query.order_by(Attendance.date.desc()).all()


def get_attendance_summary(records):
    total = len(records)
    present = sum(1 for r in records if r.status == "Present")
    absent = sum(1 for r in records if r.status == "Absent")
    return total, present, absent


def get_student_attendance(roll_number):
    student = Student.query.filter_by(roll_number=(roll_number or "").strip()).first()

    if student is None:
        return []

    records = Attendance.query.filter_by(student_id=student.id).order_by(Attendance.date.desc()).all()

    return [
        {
            **r.to_dict(),
            "subject_name": r.subject.subject_name,
        }
        for r in records
    ]
