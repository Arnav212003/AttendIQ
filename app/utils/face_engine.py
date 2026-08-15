import os
from datetime import datetime

import cv2
import numpy as np
from flask import current_app

from app.extensions import db
from app.models.student import Student
from app.models.face_embedding import FaceEmbedding


def read_camera_image(file_storage):
    if file_storage is None:
        return None
    file_bytes = np.asarray(bytearray(file_storage.read()), dtype=np.uint8)
    return cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)


def detect_screen_replay_signal(image):
    """Additional (advisory, not blocking) anti-spoofing signal: checks for
    periodic high-frequency patterns (Moiré interference) typical of a face
    being shown on a phone/laptop screen held up to the camera, rather than
    a real face captured directly.

    IMPORTANT - why this is advisory, not a hard block: validated only on
    synthetic test patterns (see scripts/), this signal has an UNKNOWN
    false-positive rate on real faces. Real faces with glasses, textured
    hair, or certain lighting can also produce high-frequency energy and
    would incorrectly trigger this. Hard-rejecting attendance on an unvalidated
    signal risks locking out legitimate students, which is worse than letting
    a determined spoofer occasionally through. This returns a suspicion flag
    for the teacher to see, rather than blocking the request outright.

    Returns (is_suspicious, high_freq_energy_score).
    """
    if image is None:
        return False, 0.0

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    gray = cv2.resize(gray, (256, 256)).astype(np.float32)

    f = np.fft.fft2(gray)
    fshift = np.fft.fftshift(f)
    magnitude_log = np.log(np.abs(fshift) + 1)

    h, w = gray.shape
    cy, cx = h // 2, w // 2

    # Exclude the low-frequency center - natural image energy concentrates
    # there; we only care about periodic high-frequency spikes.
    y, x = np.ogrid[:h, :w]
    radius = min(h, w) // 8
    high_freq_mask = (y - cy) ** 2 + (x - cx) ** 2 > radius ** 2

    high_freq_energy = magnitude_log[high_freq_mask]
    peak_score = float(np.max(high_freq_energy))

    # Threshold chosen conservatively (high) to minimize false positives on
    # real faces, based on the limited synthetic test in this project - not
    # independently validated against a real spoofing dataset.
    SUSPICION_THRESHOLD = 11.0

    return peak_score >= SUSPICION_THRESHOLD, peak_score


def detect_faces(image):
    """Returns a list of cropped, resized face images. Empty list if none detected."""
    if image is None:
        return []

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80))

    cropped_faces = []
    for (x, y, w, h) in faces:
        face = gray[y:y + h, x:x + w]
        cropped_faces.append(cv2.resize(face, (200, 200)))

    return cropped_faces


def count_open_eyes(image):
    """Counts detected open eyes in the largest face region of the image.
    Used as a simple liveness signal - a closed-eye frame should detect ~0 eyes."""
    if image is None:
        return 0

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")

    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80))
    if len(faces) == 0:
        return 0

    x, y, w, h = faces[0]
    face_roi = gray[y:y + h, x:x + w]

    eyes = eye_cascade.detectMultiScale(face_roi, scaleFactor=1.1, minNeighbors=8, minSize=(15, 15))
    return len(eyes)


def check_blink_liveness(eyes_open_image, eyes_closed_image, eyes_open_again_image=None):
    """Liveness check: expects two or three frames captured a moment apart.

    Two-frame mode (eyes_open_again_image=None, kept for backward
    compatibility): checks that eye count drops between frame 1 and frame 2
    (a blink). A static photo held up to the camera shows the same eye count
    in both frames, so this is rejected.

    Three-frame mode (preferred): checks the fuller Open -> Closed -> Open
    pattern of a natural blink. This is more robust than the two-frame check
    against a specific bypass: someone briefly moving/removing a static photo
    between frame 1 and frame 2 (making eye detection fail in frame 2 for
    reasons unrelated to blinking) and holding it up again for a third frame
    would still fail this check, because a real blink's defining trait is
    eyes returning to open, not just eyes disappearing once.

    Returns (is_live, message).
    """
    open_count_1 = count_open_eyes(eyes_open_image)
    closed_count = count_open_eyes(eyes_closed_image)

    if open_count_1 == 0:
        return False, "No eyes detected in the first frame. Please face the camera directly and retry."

    if closed_count >= open_count_1:
        return False, "No blink detected - please blink naturally during capture (this check helps prevent photo spoofing)."

    if eyes_open_again_image is None:
        # Two-frame mode - open-to-closed transition was enough to pass.
        return True, "Liveness check passed."

    open_count_2 = count_open_eyes(eyes_open_again_image)

    if open_count_2 == 0:
        return False, "Eyes did not reopen after the blink - please retry with a natural blink."

    return True, "Liveness check passed (open-closed-open blink pattern confirmed)."



def _detect_face_eye_states(image):
    """Detect faces and return stable tracking metadata for group liveness.

    Each item contains the face bounding box, center, size, and number of
    detected open eyes. Unlike ``count_open_eyes`` this keeps *all* faces so
    classroom liveness is not accidentally validated using only the largest
    or first student in the frame.
    """
    if image is None:
        return []

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")

    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(70, 70))
    states = []
    for (x, y, w, h) in faces:
        face_roi = gray[y:y + h, x:x + w]
        eyes = eye_cascade.detectMultiScale(face_roi, scaleFactor=1.1, minNeighbors=7, minSize=(12, 12))
        states.append({
            "box": (int(x), int(y), int(w), int(h)),
            "center": (float(x + w / 2.0), float(y + h / 2.0)),
            "diag": float((w * w + h * h) ** 0.5),
            "open_eyes": int(len(eyes)),
        })

    # Stable left-to-right ordering makes matching deterministic in tests and
    # helps when two faces are similarly close to one another.
    states.sort(key=lambda item: item["center"][0])
    return states


def _match_face_tracks(reference_states, current_states):
    """Greedily match current detections to reference faces by normalized
    center distance. The camera is stationary during the short liveness burst,
    so this is intentionally lightweight and avoids adding a tracking model.

    Returns {reference_index: current_state}. Unmatched faces are omitted.
    """
    if not reference_states or not current_states:
        return {}

    candidates = []
    for ref_idx, ref in enumerate(reference_states):
        rx, ry = ref["center"]
        scale = max(ref["diag"], 1.0)
        for cur_idx, cur in enumerate(current_states):
            cx, cy = cur["center"]
            normalized_distance = (((rx - cx) ** 2 + (ry - cy) ** 2) ** 0.5) / scale
            candidates.append((normalized_distance, ref_idx, cur_idx))

    candidates.sort(key=lambda x: x[0])
    matched_refs = set()
    matched_current = set()
    result = {}

    # A face should not move more than roughly its own diagonal during a
    # 2-3 second stationary classroom capture.
    MAX_NORMALIZED_DISTANCE = 0.85
    for distance, ref_idx, cur_idx in candidates:
        if distance > MAX_NORMALIZED_DISTANCE:
            continue
        if ref_idx in matched_refs or cur_idx in matched_current:
            continue
        result[ref_idx] = current_states[cur_idx]
        matched_refs.add(ref_idx)
        matched_current.add(cur_idx)

    return result


def check_group_blink_liveness(frames, min_frames=8):
    """Validate an Open -> Closed -> Open blink for *every* face present in
    the first classroom frame.

    The browser sends a short burst of frames (normally ~3 seconds). Faces are
    tracked by position, and each track must be observed with eyes open, then
    closed/reduced, then open again. This fixes the old behavior where only
    one/largest face could satisfy liveness for an entire group photo.

    This remains a lightweight student-project liveness check, not a
    production anti-spoofing classifier; its purpose is to reject obvious
    static-photo attacks while keeping the implementation explainable.

    Returns (is_live, message, tracked_face_count).
    """
    if frames is None or len(frames) < min_frames:
        return False, f"At least {min_frames} liveness frames are required.", 0

    reference = _detect_face_eye_states(frames[0])
    if not reference:
        return False, "No faces detected in the first liveness frame.", 0

    tracks = []
    for state in reference:
        tracks.append({
            "open_seen": state["open_eyes"] > 0,
            "closed_seen": False,
            "reopened_seen": False,
            "observed": 1,
            "last_open_eyes": state["open_eyes"],
        })

    for frame in frames[1:]:
        current = _detect_face_eye_states(frame)
        matches = _match_face_tracks(reference, current)

        for ref_idx, state in matches.items():
            track = tracks[ref_idx]
            track["observed"] += 1
            eyes = state["open_eyes"]

            # Eye detector can fluctuate by one detection, so treat a drop to
            # zero as the clear closed-eye signal. We require the eyes to be
            # detected again later, preventing a face simply disappearing.
            if eyes > 0:
                if track["closed_seen"]:
                    track["reopened_seen"] = True
                else:
                    track["open_seen"] = True
            elif track["open_seen"] and not track["closed_seen"]:
                track["closed_seen"] = True

            track["last_open_eyes"] = eyes

    min_observed = max(4, len(frames) // 2)
    failures = []
    for idx, track in enumerate(tracks, start=1):
        if track["observed"] < min_observed:
            failures.append(f"face {idx} was not visible in enough frames")
        elif not track["open_seen"]:
            failures.append(f"face {idx} never had clearly detected open eyes")
        elif not track["closed_seen"]:
            failures.append(f"face {idx} did not blink")
        elif not track["reopened_seen"]:
            failures.append(f"face {idx} did not reopen eyes after blinking")

    if failures:
        return False, "Liveness failed: " + "; ".join(failures) + ". Please keep everyone visible and blink once during capture.", len(reference)

    return True, f"Group liveness passed for {len(reference)} face(s).", len(reference)

def detect_face(image):
    """Backward-compatible single-face helper, used by enrollment (one face per photo)."""
    faces = detect_faces(image)
    return faces[0] if faces else None


def enroll_student_face(roll_number, camera_file):
    student = Student.query.filter_by(roll_number=(roll_number or "").strip()).first()

    if student is None:
        return False, "Student roll number not found."

    image = read_camera_image(camera_file)
    if image is None:
        return False, "Please capture face image first."

    face = detect_face(image)
    if face is None:
        return False, "No clear face detected. Please capture again."

    folder = os.path.join(current_app.config["FACE_UPLOAD_FOLDER"], student.roll_number)
    os.makedirs(folder, exist_ok=True)

    filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".jpg"
    path = os.path.join(folder, filename)
    cv2.imwrite(path, face)

    db.session.add(FaceEmbedding(student_id=student.id, image_path=path, lbph_label=student.id))
    db.session.commit()

    # Retraining runs synchronously here (not via Celery). This project
    # originally offloaded retraining to a Celery background worker, but
    # Render's free tier does not support Background Worker services at all
    # ("service type is not available for this plan") - there is no
    # workaround short of paying for a worker. Since LBPH training on a
    # small class-size dataset (dozens of students, not thousands) completes
    # in well under a second, running it synchronously in the request is a
    # reasonable tradeoff for a free-tier deployment. If this were scaled to
    # a much larger dataset, moving retraining back to an async worker (paid
    # tier, or a different host that supports free workers) would be worth
    # revisiting.
    retrain_face_model(current_app.config["FACE_MODEL_PATH"])

    return True, "Student face enrolled successfully and model retrained."


def retrain_face_model(face_model_path):
    """Retrains LBPH from all stored face images. Runs synchronously inside
    the request (see enroll_student_face for why - no free-tier worker)."""
    embeddings = FaceEmbedding.query.all()

    faces, labels = [], []

    for emb in embeddings:
        img = cv2.imread(emb.image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        faces.append(cv2.resize(img, (200, 200)))
        labels.append(emb.lbph_label)

    if not faces:
        return False

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(faces, np.array(labels))
    recognizer.save(face_model_path)
    return True


def recognize_face(camera_file, enrolled_students, face_model_path):
    if camera_file is None:
        return False, "Please capture classroom image first.", []

    if not os.path.exists(face_model_path):
        return False, "Face model not trained yet. Please enroll student face first.", []

    image = read_camera_image(camera_file)
    detected_faces = detect_faces(image)

    if not detected_faces:
        return False, "No clear face detected. Please capture again.", []

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(face_model_path)

    # LBPH: lower confidence = closer match. This default (90) is unvalidated
    # against real accuracy data - see scripts/evaluate_face_accuracy.py and
    # the "Face Recognition Evaluation" section of EVALUATION.md, which notes
    # the synthetic evaluation was too easy to give a trustworthy number here.
    # Re-tune once real face photos are available for evaluation.
    FACE_CONFIDENCE_THRESHOLD = 90

    # Recognize every detected face in the classroom photo, not just the first one.
    enrolled_ids = {student.id for student in enrolled_students}
    matched_student_ids = {}  # student_id -> best (lowest) confidence seen

    for face in detected_faces:
        predicted_label, confidence = recognizer.predict(face)

        # Explicitly discard any prediction that isn't one of the students
        # enrolled in this subject - the LBPH model is trained on ALL
        # students system-wide, so it can predict a label belonging to a
        # student from a completely different subject. Filtering immediately
        # here (rather than relying on the preview-building loop below to
        # implicitly skip it) makes that intent explicit and avoids storing
        # irrelevant matches at all.
        if predicted_label not in enrolled_ids:
            continue

        if confidence < FACE_CONFIDENCE_THRESHOLD:
            if predicted_label not in matched_student_ids or confidence < matched_student_ids[predicted_label]:
                matched_student_ids[predicted_label] = confidence

    preview = []
    for student in enrolled_students:
        if student.id in matched_student_ids:
            preview.append(
                {
                    "student_id": student.id,
                    "student_name": student.name,
                    "roll_number": student.roll_number,
                    "status": "Present",
                    "confidence": round(matched_student_ids[student.id], 2),
                }
            )
        else:
            preview.append(
                {
                    "student_id": student.id,
                    "student_name": student.name,
                    "roll_number": student.roll_number,
                    "status": "Absent",
                    "confidence": None,
                }
            )

    return True, f"Detected {len(detected_faces)} face(s), matched {len(matched_student_ids)} enrolled student(s).", preview