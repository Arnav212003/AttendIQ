from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.attendance_service import (
    save_manual_attendance,
    save_attendance,
    filter_attendance,
    get_attendance_summary,
)
from app.models.subject import Subject
from app.services.enrollment_service import get_enrolled_student_ids


attendance_bp = Blueprint("attendance", __name__)


def _verify_subject_ownership(subject_id, teacher_id):
    """Returns (subject, error_response) - error_response is None if ownership is valid."""
    subject = Subject.query.get(subject_id)

    if subject is None:
        return None, (jsonify({"success": False, "message": "Subject not found."}), 404)

    if str(subject.teacher_id) != str(teacher_id):
        return None, (jsonify({"success": False, "message": "You do not have access to this subject."}), 403)

    return subject, None


def _filter_to_enrolled_only(subject_id, attendance_data):
    """Drops any attendance entries whose student_id isn't actually enrolled in this subject.
    Prevents submitting attendance for unrelated students via a tampered request."""
    enrolled_ids = get_enrolled_student_ids(subject_id)
    return [entry for entry in attendance_data if entry.get("student_id") in enrolled_ids]


@attendance_bp.post("/manual")
@jwt_required()
def mark_manual_attendance():
    teacher_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    subject_id = data.get("subject_id")

    _, error = _verify_subject_ownership(subject_id, teacher_id)
    if error:
        return error

    attendance_data = _filter_to_enrolled_only(subject_id, data.get("attendance_data", []))
    success, message = save_manual_attendance(subject_id, attendance_data)

    return jsonify({"success": success, "message": message}), (200 if success else 400)


@attendance_bp.post("/confirm")
@jwt_required()
def confirm_ai_attendance():
    """Confirms a face/voice recognition preview and persists it."""
    teacher_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    subject_id = data.get("subject_id")

    _, error = _verify_subject_ownership(subject_id, teacher_id)
    if error:
        return error

    attendance_data = _filter_to_enrolled_only(subject_id, data.get("attendance_data", []))
    success, message = save_attendance(
        subject_id,
        attendance_data,
        attendance_mode=data.get("mode", "Face Recognition"),
    )

    return jsonify({"success": success, "message": message}), (200 if success else 400)


@attendance_bp.get("/")
@jwt_required()
def view_attendance():
    teacher_id = get_jwt_identity()
    subject_id = request.args.get("subject_id", type=int)
    attendance_date = request.args.get("date")

    if subject_id:
        _, error = _verify_subject_ownership(subject_id, teacher_id)
        if error:
            return error

    records = filter_attendance(subject_id=subject_id, attendance_date=attendance_date, teacher_id=teacher_id)
    total, present, absent = get_attendance_summary(records)

    return jsonify(
        {
            "success": True,
            "summary": {"total": total, "present": present, "absent": absent},
            "records": [r.to_dict() for r in records],
        }
    ), 200
