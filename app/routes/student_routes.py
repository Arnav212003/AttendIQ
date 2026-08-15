from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app.extensions import limiter
from app.services.student_service import add_student, get_all_students, get_student_by_roll, verify_student_pin
from app.services.enrollment_service import join_subject, get_student_subjects
from app.services.attendance_service import get_student_attendance


student_bp = Blueprint("students", __name__)


@student_bp.post("/")
@jwt_required()
def create_student():
    data = request.get_json(silent=True) or {}

    success, message, student, plain_pin = add_student(
        data.get("name"),
        data.get("roll_number"),
        data.get("class_section"),
        data.get("email_phone"),
    )

    if not success:
        return jsonify({"success": False, "message": message}), 400

    # plain_pin is shown here only, once, at registration time - the teacher
    # must share it with the student out-of-band (never retrievable again).
    return jsonify({
        "success": True,
        "message": message,
        "student": student.to_dict(include_pin=plain_pin),
    }), 201


@student_bp.get("/")
@jwt_required()
def list_students():
    students = get_all_students()
    return jsonify({"success": True, "students": [s.to_dict() for s in students]}), 200


@student_bp.post("/join-subject")
@limiter.limit("10 per minute")
def join_subject_route():
    # Student-facing, no teacher JWT required - roll_number + PIN act as identity here.
    data = request.get_json(silent=True) or {}

    success, message = join_subject(
        data.get("roll_number"), data.get("subject_code"), data.get("pin_code")
    )
    status_code = 200 if success else 400

    return jsonify({"success": success, "message": message}), status_code


@student_bp.post("/<roll_number>/subjects")
@limiter.limit("10 per minute")
def student_subjects_route(roll_number):
    """PIN-protected + rate-limited: prevents brute-forcing another
    student's PIN by guessing, and prevents roll-number-only lookups."""
    data = request.get_json(silent=True) or {}
    pin_code = data.get("pin_code")

    student = verify_student_pin(roll_number, pin_code)
    if student is None:
        return jsonify({"success": False, "message": "Invalid roll number or PIN."}), 401

    subjects = get_student_subjects(roll_number)
    return jsonify({"success": True, "subjects": subjects}), 200


@student_bp.post("/<roll_number>/attendance")
@limiter.limit("10 per minute")
def student_attendance_route(roll_number):
    """PIN-protected + rate-limited: see student_subjects_route above."""
    data = request.get_json(silent=True) or {}
    pin_code = data.get("pin_code")

    student = verify_student_pin(roll_number, pin_code)
    if student is None:
        return jsonify({"success": False, "message": "Invalid roll number or PIN."}), 401

    records = get_student_attendance(roll_number)
    return jsonify({"success": True, "attendance": records}), 200
