import random

from app.extensions import db
from app.models.student import Student


def generate_pin():
    return f"{random.randint(0, 9999):04d}"


def add_student(name, roll_number, class_section, email_phone):
    roll_number = (roll_number or "").strip()

    if not name or not roll_number:
        return False, "Name and roll number are required.", None, None

    if Student.query.filter_by(roll_number=roll_number).first():
        return False, "Student with this roll number already exists.", None, None

    plain_pin = generate_pin()

    student = Student(
        name=name.strip(),
        roll_number=roll_number,
        class_section=(class_section or "").strip(),
        email_phone=(email_phone or "").strip(),
    )
    student.set_pin(plain_pin)

    db.session.add(student)
    db.session.commit()

    # plain_pin is only ever available here, right after creation - it is
    # never stored or retrievable again after this point.
    return True, "Student registered successfully.", student, plain_pin


def get_all_students():
    return Student.query.order_by(Student.id).all()


def get_student_by_roll(roll_number):
    return Student.query.filter_by(roll_number=(roll_number or "").strip()).first()


def verify_student_pin(roll_number, pin_code):
    student = Student.query.filter_by(roll_number=(roll_number or "").strip()).first()

    if student is None:
        return None

    if not student.check_pin(pin_code):
        return None

    return student
