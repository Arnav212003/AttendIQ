from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.utils.face_engine import (
    enroll_student_face,
    recognize_face,
    read_camera_image,
    check_group_blink_liveness,
    detect_screen_replay_signal,
)
from app.models.student import Student
from app.models.subject import Subject
from app.services.enrollment_service import get_enrolled_student_ids, teacher_has_student


face_bp = Blueprint("face", __name__)


@face_bp.post("/enroll")
@jwt_required()
def enroll_face_route():
    teacher_id = get_jwt_identity()
    roll_number = request.form.get("roll_number")
    camera_file = request.files.get("image")

    if not roll_number:
        return jsonify({"success": False, "message": "roll_number is required."}), 400

    student = Student.query.filter_by(roll_number=roll_number.strip()).first()
    if student is None:
        return jsonify({"success": False, "message": "Student roll number not found."}), 404

    if not teacher_has_student(teacher_id, student.id):
        return jsonify({
            "success": False,
            "message": "This student is not enrolled in any of your subjects."
        }), 403

    success, message = enroll_student_face(roll_number, camera_file)
    return jsonify({"success": success, "message": message}), (200 if success else 400)


@face_bp.post("/recognize")
@jwt_required()
def recognize_face_route():
    """Recognize all enrolled students in a classroom image with mandatory
    group liveness. The browser sends ``image`` plus a burst of
    ``liveness_frames`` captured over ~3 seconds. Every face visible in the
    first liveness frame must complete an Open -> Closed -> Open blink.
    """
    teacher_id = get_jwt_identity()
    camera_file = request.files.get("image")
    liveness_files = request.files.getlist("liveness_frames")
    subject_id = request.form.get("subject_id", type=int)

    if not subject_id:
        return jsonify({"success": False, "message": "subject_id is required."}), 400

    if camera_file is None or len(liveness_files) < 8:
        return jsonify({
            "success": False,
            "message": "A classroom image and at least 8 liveness frames are required."
        }), 400

    subject = Subject.query.get(subject_id)
    if subject is None:
        return jsonify({"success": False, "message": "Subject not found."}), 404
    if str(subject.teacher_id) != str(teacher_id):
        return jsonify({"success": False, "message": "You do not have access to this subject."}), 403

    frames = []
    for file_storage in liveness_files:
        image = read_camera_image(file_storage)
        if image is not None:
            frames.append(image)

    is_live, liveness_message, live_face_count = check_group_blink_liveness(frames)
    if not is_live:
        return jsonify({"success": False, "message": liveness_message}), 400

    camera_file.seek(0)
    first_image = read_camera_image(camera_file)
    is_suspicious, replay_score = detect_screen_replay_signal(first_image)
    camera_file.seek(0)

    enrolled_ids = get_enrolled_student_ids(subject_id)
    enrolled_students = Student.query.filter(Student.id.in_(enrolled_ids)).all()

    success, message, preview = recognize_face(
        camera_file, enrolled_students, current_app.config["FACE_MODEL_PATH"]
    )

    if not success:
        return jsonify({"success": False, "message": message}), 400

    response = {
        "success": True,
        "message": f"{message} Group liveness verified for {live_face_count} face(s).",
        "preview": preview,
    }

    if is_suspicious:
        response["liveness_warning"] = (
            f"Possible screen replay detected (unvalidated heuristic, score={replay_score:.1f}). "
            "Please review this attendance manually before confirming."
        )

    return jsonify(response), 200

