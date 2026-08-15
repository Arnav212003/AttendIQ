from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models.teacher import Teacher


teacher_bp = Blueprint("teachers", __name__)


@teacher_bp.get("/me")
@jwt_required()
def get_current_teacher():
    teacher_id = get_jwt_identity()
    teacher = Teacher.query.get(teacher_id)

    if teacher is None:
        return jsonify({"success": False, "message": "Teacher not found."}), 404

    return jsonify({"success": True, "teacher": teacher.to_dict()}), 200
