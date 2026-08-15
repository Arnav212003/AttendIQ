from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.enrollment import Enrollment
from app.models.student import Student
from app.models.subject import Subject


def join_subject(roll_number, subject_code, pin_code):
    student = Student.query.filter_by(roll_number=(roll_number or "").strip()).first()

    if student is None:
        return False, "Student roll number not found."

    if not student.check_pin(pin_code):
        return False, "Invalid PIN."

    subject = Subject.query.filter_by(subject_code=(subject_code or "").strip().upper()).first()

    if subject is None:
        return False, "Invalid subject code."

    enrollment = Enrollment(student_id=student.id, subject_id=subject.id)
    db.session.add(enrollment)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False, "Student already enrolled in this subject."

    return True, f"Successfully joined {subject.subject_name}."


def get_student_subjects(roll_number):
    student = Student.query.filter_by(roll_number=(roll_number or "").strip()).first()

    if student is None:
        return []

    return [
        {
            "subject_name": e.subject.subject_name,
            "subject_code": e.subject.subject_code,
            "section": e.subject.section,
        }
        for e in student.enrollments
    ]


def get_subject_students(subject_id):
    subject = Subject.query.get(subject_id)

    if subject is None:
        return []

    return [
        {
            "student_id": e.student.id,
            "name": e.student.name,
            "roll_number": e.student.roll_number,
            "class_section": e.student.class_section,
        }
        for e in subject.enrollments
    ]


def get_enrolled_student_ids(subject_id):
    """Returns a set of student_ids actually enrolled in this subject.
    Used to validate client-supplied student_ids before recognition/attendance."""
    subject = Subject.query.get(subject_id)

    if subject is None:
        return set()

    return {e.student_id for e in subject.enrollments}


def teacher_has_student(teacher_id, student_id):
    """Returns True if the given student is enrolled in at least one subject
    taught by this teacher. Used to gate biometric enrollment - a teacher
    should only be able to enroll face/voice for their own students."""
    return (
        Enrollment.query
        .join(Subject, Enrollment.subject_id == Subject.id)
        .filter(
            Enrollment.student_id == student_id,
            Subject.teacher_id == teacher_id,
        )
        .first()
        is not None
    )
