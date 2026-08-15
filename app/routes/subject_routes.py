from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.subject_service import create_subject, get_all_subjects, get_subject_by_code
from app.services.enrollment_service import get_subject_students
from app.services.qr_service import create_subject_qr, get_share_message
from app.models.subject import Subject


subject_bp = Blueprint("subjects", __name__)


@subject_bp.post("/")
@jwt_required()
def create_subject_route():
    teacher_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    success, message, subject = create_subject(
        data.get("subject_name"), data.get("section"), teacher_id
    )

    if not success:
        return jsonify({"success": False, "message": message}), 400

    return jsonify({"success": True, "message": message, "subject": subject.to_dict()}), 201


@subject_bp.get("/")
@jwt_required()
def list_subjects_route():
    teacher_id = get_jwt_identity()
    subjects = get_all_subjects(teacher_id=teacher_id)
    return jsonify({"success": True, "subjects": [s.to_dict() for s in subjects]}), 200


@subject_bp.get("/<int:subject_id>/students")
@jwt_required()
def subject_students_route(subject_id):
    teacher_id = get_jwt_identity()
    subject = Subject.query.get_or_404(subject_id)

    if str(subject.teacher_id) != str(teacher_id):
        return jsonify({"success": False, "message": "You do not have access to this subject."}), 403

    students = get_subject_students(subject_id)
    return jsonify({"success": True, "students": students}), 200


@subject_bp.get("/<int:subject_id>/qr")
@jwt_required()
def subject_qr_route(subject_id):
    teacher_id = get_jwt_identity()
    subject = Subject.query.get_or_404(subject_id)

    if str(subject.teacher_id) != str(teacher_id):
        return jsonify({"success": False, "message": "You do not have access to this subject."}), 403

    qr_buffer = create_subject_qr(subject.subject_code)
    return send_file(qr_buffer, mimetype="image/png", download_name=f"{subject.subject_code}_qr.png")


@subject_bp.get("/<int:subject_id>/share-message")
@jwt_required()
def subject_share_message_route(subject_id):
    teacher_id = get_jwt_identity()
    subject = Subject.query.get_or_404(subject_id)

    if str(subject.teacher_id) != str(teacher_id):
        return jsonify({"success": False, "message": "You do not have access to this subject."}), 403

    message = get_share_message(subject.subject_name, subject.subject_code, subject.section)
    return jsonify({"success": True, "message": message, "subject_code": subject.subject_code}), 200
