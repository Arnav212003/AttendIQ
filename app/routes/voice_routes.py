import secrets

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.utils.voice_engine import (
    enroll_student_voice,
    recognize_voice,
    check_audio_replay,
    _load_wav_as_float_array,
    detect_narrow_bandwidth_signal,
    verify_voice_liveness_pattern,
)
from app.models.student import Student
from app.models.subject import Subject
from app.services.enrollment_service import get_enrolled_student_ids, teacher_has_student


voice_bp = Blueprint("voice", __name__)


@voice_bp.post("/enroll")
@jwt_required()
def enroll_voice_route():
    teacher_id = get_jwt_identity()
    roll_number = request.form.get("roll_number")
    audio_file = request.files.get("audio")

    if not roll_number:
        return jsonify({"success": False, "message": "roll_number is required."}), 400

    student = Student.query.filter_by(roll_number=roll_number.strip()).first()
    if student is None:
        return jsonify({"success": False, "message": "Student roll number not found."}), 404

    # Only a teacher who actually teaches this student may enroll their biometrics.
    if not teacher_has_student(teacher_id, student.id):
        return jsonify({
            "success": False,
            "message": "This student is not enrolled in any of your subjects."
        }), 403

    success, message = enroll_student_voice(roll_number, audio_file)
    return jsonify({"success": success, "message": message}), (200 if success else 400)


def _voice_challenge_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="attendiq-voice-liveness-v1")


@voice_bp.get("/challenge")
@jwt_required()
def voice_liveness_challenge_route():
    """Issue a short-lived, signed randomized timing challenge for voice
    recognition. No server-side session state is required; subject/teacher
    binding is carried inside the signed token and validated on submission.
    """
    teacher_id = get_jwt_identity()
    subject_id = request.args.get("subject_id", type=int)
    if not subject_id:
        return jsonify({"success": False, "message": "subject_id is required."}), 400

    subject = Subject.query.get(subject_id)
    if subject is None:
        return jsonify({"success": False, "message": "Subject not found."}), 404
    if str(subject.teacher_id) != str(teacher_id):
        return jsonify({"success": False, "message": "You do not have access to this subject."}), 403

    pattern = secrets.choice(["short_long", "long_short"])
    nonce = secrets.token_hex(12)
    token = _voice_challenge_serializer().dumps({
        "teacher_id": str(teacher_id),
        "subject_id": subject_id,
        "pattern": pattern,
        "nonce": nonce,
    })

    instructions = {
        "short_long": "Make a short 'AA' sound, pause clearly, then hold 'AAAA' for about 2 seconds.",
        "long_short": "Hold 'AAAA' for about 2 seconds, pause clearly, then make a short 'AA' sound.",
    }
    return jsonify({
        "success": True,
        "challenge_token": token,
        "pattern": pattern,
        "instruction": instructions[pattern],
        "expires_in_seconds": 120,
    }), 200


@voice_bp.post("/recognize")
@jwt_required()
def recognize_voice_route():
    teacher_id = get_jwt_identity()
    audio_file = request.files.get("audio")
    subject_id = request.form.get("subject_id", type=int)
    challenge_token = request.form.get("challenge_token", "")

    if not subject_id:
        return jsonify({"success": False, "message": "subject_id is required."}), 400

    subject = Subject.query.get(subject_id)
    if subject is None:
        return jsonify({"success": False, "message": "Subject not found."}), 404
    if str(subject.teacher_id) != str(teacher_id):
        return jsonify({"success": False, "message": "You do not have access to this subject."}), 403

    if audio_file is None:
        return jsonify({"success": False, "message": "audio is required."}), 400
    if not challenge_token:
        return jsonify({"success": False, "message": "A fresh voice liveness challenge is required."}), 400

    try:
        challenge = _voice_challenge_serializer().loads(challenge_token, max_age=120)
    except SignatureExpired:
        return jsonify({"success": False, "message": "Voice liveness challenge expired. Please record again."}), 400
    except BadSignature:
        return jsonify({"success": False, "message": "Invalid voice liveness challenge."}), 400

    if (
        int(challenge.get("subject_id", -1)) != subject_id
        or str(challenge.get("teacher_id")) != str(teacher_id)
        or challenge.get("pattern") not in {"short_long", "long_short"}
    ):
        return jsonify({"success": False, "message": "Voice liveness challenge does not match this request."}), 400

    audio_file.seek(0)
    wav_array = _load_wav_as_float_array(audio_file)
    if wav_array is None:
        return jsonify({"success": False, "message": "Could not decode voice recording."}), 400

    is_live, liveness_message = verify_voice_liveness_pattern(wav_array, challenge["pattern"])
    if not is_live:
        return jsonify({"success": False, "message": liveness_message}), 400

    # Keep exact-file replay detection as a second independent signal. The
    # randomized active challenge above is the primary liveness mechanism.
    audio_file.seek(0)
    is_new, replay_message = check_audio_replay(audio_file, subject_id, challenge.get("nonce"))
    if not is_new:
        return jsonify({"success": False, "message": replay_message}), 400

    is_suspicious, bandwidth_hz = detect_narrow_bandwidth_signal(wav_array)
    audio_file.seek(0)

    enrolled_ids = get_enrolled_student_ids(subject_id)
    enrolled_students = Student.query.filter(Student.id.in_(enrolled_ids)).all()

    success, message, preview = recognize_voice(audio_file, enrolled_students)

    if not success:
        return jsonify({"success": False, "message": message}), 400

    response = {
        "success": True,
        "message": f"{message} {liveness_message}",
        "preview": preview,
    }

    if is_suspicious:
        response["liveness_warning"] = (
            f"Unusually narrow audio bandwidth detected (unvalidated heuristic, "
            f"~{bandwidth_hz:.0f}Hz). Please review this attendance manually before confirming."
        )

    return jsonify(response), 200

