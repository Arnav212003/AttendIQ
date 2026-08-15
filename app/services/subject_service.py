import random
import string

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.subject import Subject


def generate_subject_code():
    letters = string.ascii_uppercase
    digits = string.digits
    return "".join(
        [
            random.choice(letters),
            random.choice(letters),
            random.choice(digits),
            random.choice(digits),
            random.choice(letters),
        ]
    )


def create_subject(subject_name, section, teacher_id):
    if not subject_name or not section:
        return False, "Subject name and section are required.", None

    for _ in range(5):  # retry on rare code collision, DB unique constraint guarantees correctness
        subject_code = generate_subject_code()

        subject = Subject(
            subject_name=subject_name.strip(),
            subject_code=subject_code,
            section=section.strip(),
            teacher_id=teacher_id,
        )

        db.session.add(subject)

        try:
            db.session.commit()
            return True, f"Subject created successfully. Subject Code: {subject_code}", subject
        except IntegrityError:
            db.session.rollback()
            continue

    return False, "Could not generate a unique subject code, please try again.", None


def get_all_subjects(teacher_id=None):
    query = Subject.query
    if teacher_id is not None:
        query = query.filter_by(teacher_id=teacher_id)
    return query.order_by(Subject.id).all()


def get_subject_by_code(subject_code):
    return Subject.query.filter_by(subject_code=(subject_code or "").strip().upper()).first()
