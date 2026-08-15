import re

from app.extensions import db
from app.models.teacher import Teacher


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def register_teacher(teacher_name, email, password, department):
    teacher_name = (teacher_name or "").strip()
    email = (email or "").strip().lower()
    password = (password or "").strip()
    department = (department or "").strip()

    if not teacher_name or not email or not password:
        return False, "Please fill all required fields.", None

    if not EMAIL_REGEX.match(email):
        return False, "Invalid email format.", None

    if len(password) < 6:
        return False, "Password must be at least 6 characters.", None

    if Teacher.query.filter_by(email=email).first():
        return False, "Teacher account already exists with this email.", None

    teacher = Teacher(teacher_name=teacher_name, email=email, department=department)
    teacher.set_password(password)

    db.session.add(teacher)
    db.session.commit()

    return True, "Teacher registered successfully.", teacher


def authenticate_teacher(email, password):
    email = (email or "").strip().lower()
    password = (password or "").strip()

    teacher = Teacher.query.filter_by(email=email).first()

    if teacher is None or not teacher.check_password(password):
        return False, "Invalid email or password.", None

    return True, "Login successful.", teacher
