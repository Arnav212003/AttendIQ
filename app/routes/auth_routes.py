from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token

from app.extensions import limiter
from app.services.auth_service import register_teacher, authenticate_teacher


auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/register")
@limiter.limit("5 per minute")
def register():
    data = request.get_json(silent=True) or {}

    success, message, teacher = register_teacher(
        data.get("teacher_name"),
        data.get("email"),
        data.get("password"),
        data.get("department"),
    )

    if not success:
        return jsonify({"success": False, "message": message}), 400

    return jsonify({"success": True, "message": message, "teacher": teacher.to_dict()}), 201


@auth_bp.post("/login")
@limiter.limit("10 per minute")
def login():
    data = request.get_json(silent=True) or {}

    success, message, teacher = authenticate_teacher(
        data.get("email"),
        data.get("password"),
    )

    if not success:
        return jsonify({"success": False, "message": message}), 401

    access_token = create_access_token(
        identity=str(teacher.id),
        additional_claims={"role": teacher.role, "email": teacher.email},
    )

    return jsonify(
        {
            "success": True,
            "message": message,
            "access_token": access_token,
            "teacher": teacher.to_dict(),
        }
    ), 200
