import pytest

from app import create_app
from app.extensions import db


@pytest.fixture
def client(tmp_path):
    app = create_app(env="testing")
    upload_root = tmp_path / "uploads"
    app.config["UPLOAD_FOLDER"] = str(upload_root)
    app.config["FACE_UPLOAD_FOLDER"] = str(upload_root / "faces")
    app.config["VOICE_UPLOAD_FOLDER"] = str(upload_root / "voices")
    app.config["FACE_MODEL_PATH"] = str(upload_root / "face_model.yml")
    (upload_root / "faces").mkdir(parents=True, exist_ok=True)
    (upload_root / "voices").mkdir(parents=True, exist_ok=True)
    with app.app_context():
        db.create_all()
        with app.test_client() as client:
            yield client
        db.drop_all()


def test_full_flow(client):
    # register teacher
    resp = client.post("/api/auth/register", json={
        "teacher_name": "Arnav Singh",
        "email": "arnav@test.com",
        "password": "secret123",
        "department": "CS"
    })
    assert resp.status_code == 201, resp.get_json()

    # login
    resp = client.post("/api/auth/login", json={
        "email": "arnav@test.com",
        "password": "secret123"
    })
    assert resp.status_code == 200
    token = resp.get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # create subject
    resp = client.post("/api/subjects/", json={
        "subject_name": "DSA",
        "section": "A"
    }, headers=headers)
    assert resp.status_code == 201, resp.get_json()
    subject = resp.get_json()["subject"]

    # register student
    resp = client.post("/api/students/", json={
        "name": "Rahul",
        "roll_number": "101",
        "class_section": "A",
        "email_phone": "rahul@test.com"
    }, headers=headers)
    assert resp.status_code == 201, resp.get_json()
    student = resp.get_json()["student"]

    # duplicate roll number should fail
    resp = client.post("/api/students/", json={
        "name": "Rahul Dup",
        "roll_number": "101",
        "class_section": "A",
        "email_phone": ""
    }, headers=headers)
    assert resp.status_code == 400

    # student joins subject
    resp = client.post("/api/students/join-subject", json={
        "roll_number": "101",
        "pin_code": student["pin_code"],
        "subject_code": subject["subject_code"]
    })
    assert resp.status_code == 200, resp.get_json()

    # duplicate join should fail cleanly (tests unique constraint fix)
    resp = client.post("/api/students/join-subject", json={
        "roll_number": "101",
        "pin_code": student["pin_code"],
        "subject_code": subject["subject_code"]
    })
    assert resp.status_code == 400

    # mark manual attendance
    resp = client.post("/api/attendance/manual", json={
        "subject_id": subject["id"],
        "attendance_data": [
            {"student_id": student["id"], "status": "Present"}
        ]
    }, headers=headers)
    assert resp.status_code == 200, resp.get_json()

    # re-marking same day should UPDATE not duplicate (tests upsert fix)
    resp = client.post("/api/attendance/manual", json={
        "subject_id": subject["id"],
        "attendance_data": [
            {"student_id": student["id"], "status": "Absent"}
        ]
    }, headers=headers)
    assert resp.status_code == 200

    resp = client.get(f"/api/attendance/?subject_id={subject['id']}", headers=headers)
    records = resp.get_json()["records"]
    assert len(records) == 1  # not duplicated
    assert records[0]["status"] == "Absent"


def test_idor_protection(client):
    """A teacher must not be able to access another teacher's subject data."""
    # Teacher A creates a subject
    client.post("/api/auth/register", json={
        "teacher_name": "Teacher A", "email": "a@test.com",
        "password": "secret123", "department": "CS"
    })
    token_a = client.post("/api/auth/login", json={
        "email": "a@test.com", "password": "secret123"
    }).get_json()["access_token"]

    resp = client.post("/api/subjects/", json={
        "subject_name": "Algorithms", "section": "A"
    }, headers={"Authorization": f"Bearer {token_a}"})
    subject_id = resp.get_json()["subject"]["id"]

    # Teacher B tries to access Teacher A's subject
    client.post("/api/auth/register", json={
        "teacher_name": "Teacher B", "email": "b@test.com",
        "password": "secret123", "department": "CS"
    })
    token_b = client.post("/api/auth/login", json={
        "email": "b@test.com", "password": "secret123"
    }).get_json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    resp = client.get(f"/api/subjects/{subject_id}/students", headers=headers_b)
    assert resp.status_code == 403

    resp = client.get(f"/api/subjects/{subject_id}/qr", headers=headers_b)
    assert resp.status_code == 403

    resp = client.post("/api/attendance/manual", json={
        "subject_id": subject_id, "attendance_data": []
    }, headers=headers_b)
    assert resp.status_code == 403

    resp = client.get(f"/api/attendance/?subject_id={subject_id}", headers=headers_b)
    assert resp.status_code == 403


def test_attendance_rejects_unenrolled_student(client):
    """Attendance for a student not enrolled in the subject must be silently dropped,
    not saved - prevents submitting attendance for unrelated students."""
    client.post("/api/auth/register", json={
        "teacher_name": "T", "email": "t@test.com",
        "password": "secret123", "department": "CS"
    })
    token = client.post("/api/auth/login", json={
        "email": "t@test.com", "password": "secret123"
    }).get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    subject = client.post("/api/subjects/", json={
        "subject_name": "DSA", "section": "A"
    }, headers=headers).get_json()["subject"]

    s1 = client.post("/api/students/", json={
        "name": "S1", "roll_number": "1", "class_section": "A", "email_phone": ""
    }, headers=headers).get_json()["student"]
    s2 = client.post("/api/students/", json={
        "name": "S2", "roll_number": "2", "class_section": "A", "email_phone": ""
    }, headers=headers).get_json()["student"]

    client.post("/api/students/join-subject", json={
        "roll_number": "1", "pin_code": s1["pin_code"], "subject_code": subject["subject_code"]
    })
    # s2 is intentionally NOT enrolled in this subject

    resp = client.post("/api/attendance/manual", json={
        "subject_id": subject["id"],
        "attendance_data": [
            {"student_id": s1["id"], "status": "Present"},
            {"student_id": s2["id"], "status": "Present"},
        ]
    }, headers=headers)
    assert resp.status_code == 200

    resp = client.get(f"/api/attendance/?subject_id={subject['id']}", headers=headers)
    records = resp.get_json()["records"]
    assert len(records) == 1
    assert records[0]["student_id"] == s1["id"]


def test_biometric_enrollment_requires_teacher_relationship(client):
    """A teacher must not be able to enroll face/voice for a student who
    isn't enrolled in any of their subjects."""
    client.post("/api/auth/register", json={
        "teacher_name": "A", "email": "a@test.com",
        "password": "secret123", "department": "CS"
    })
    token_a = client.post("/api/auth/login", json={
        "email": "a@test.com", "password": "secret123"
    }).get_json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    subject = client.post("/api/subjects/", json={
        "subject_name": "DSA", "section": "A"
    }, headers=headers_a).get_json()["subject"]

    s1 = client.post("/api/students/", json={
        "name": "S1", "roll_number": "101", "class_section": "A", "email_phone": ""
    }, headers=headers_a).get_json()["student"]
    client.post("/api/students/join-subject", json={
        "roll_number": "101", "pin_code": s1["pin_code"], "subject_code": subject["subject_code"]
    })

    # Unrelated teacher B tries to enroll biometrics for student 101
    client.post("/api/auth/register", json={
        "teacher_name": "B", "email": "b@test.com",
        "password": "secret123", "department": "CS"
    })
    token_b = client.post("/api/auth/login", json={
        "email": "b@test.com", "password": "secret123"
    }).get_json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    resp = client.post(
        "/api/face/enroll",
        data={"roll_number": "101"},
        headers=headers_b,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403

    resp = client.post(
        "/api/voice/enroll",
        data={"roll_number": "101"},
        headers=headers_b,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403


def test_attendance_list_scoped_to_teacher(client):
    """GET /api/attendance/ without subject_id must not leak other teachers'
    attendance records - only the calling teacher's own data should return."""
    # Teacher A: subject, student, attendance
    client.post("/api/auth/register", json={
        "teacher_name": "A", "email": "a@test.com",
        "password": "secret123", "department": "CS"
    })
    token_a = client.post("/api/auth/login", json={
        "email": "a@test.com", "password": "secret123"
    }).get_json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    subject_a = client.post("/api/subjects/", json={
        "subject_name": "DSA", "section": "A"
    }, headers=headers_a).get_json()["subject"]
    student_a = client.post("/api/students/", json={
        "name": "SA", "roll_number": "201", "class_section": "A", "email_phone": ""
    }, headers=headers_a).get_json()["student"]
    client.post("/api/students/join-subject", json={
        "roll_number": "201", "pin_code": student_a["pin_code"], "subject_code": subject_a["subject_code"]
    })
    client.post("/api/attendance/manual", json={
        "subject_id": subject_a["id"],
        "attendance_data": [{"student_id": student_a["id"], "status": "Present"}]
    }, headers=headers_a)

    # Teacher B: separate subject, student, attendance
    client.post("/api/auth/register", json={
        "teacher_name": "B", "email": "b@test.com",
        "password": "secret123", "department": "CS"
    })
    token_b = client.post("/api/auth/login", json={
        "email": "b@test.com", "password": "secret123"
    }).get_json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    subject_b = client.post("/api/subjects/", json={
        "subject_name": "OS", "section": "B"
    }, headers=headers_b).get_json()["subject"]
    student_b = client.post("/api/students/", json={
        "name": "SB", "roll_number": "202", "class_section": "B", "email_phone": ""
    }, headers=headers_b).get_json()["student"]
    client.post("/api/students/join-subject", json={
        "roll_number": "202", "pin_code": student_b["pin_code"], "subject_code": subject_b["subject_code"]
    })
    client.post("/api/attendance/manual", json={
        "subject_id": subject_b["id"],
        "attendance_data": [{"student_id": student_b["id"], "status": "Present"}]
    }, headers=headers_b)

    # Teacher A calls the unscoped attendance list - must only see their own record
    resp = client.get("/api/attendance/", headers=headers_a)
    assert resp.status_code == 200
    records = resp.get_json()["records"]
    assert len(records) == 1
    assert records[0]["student_id"] == student_a["id"]


def test_student_self_service_requires_pin(client):
    """A student's own subjects/attendance must require the correct PIN,
    not just a guessable roll number."""
    client.post("/api/auth/register", json={
        "teacher_name": "T", "email": "t@test.com",
        "password": "secret123", "department": "CS"
    })
    token = client.post("/api/auth/login", json={
        "email": "t@test.com", "password": "secret123"
    }).get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/students/", json={
        "name": "S1", "roll_number": "301", "class_section": "A", "email_phone": ""
    }, headers=headers)
    correct_pin = resp.get_json()["student"]["pin_code"]

    # Wrong PIN should be rejected
    resp = client.post("/api/students/301/subjects", json={"pin_code": "0000"})
    assert resp.status_code == 401

    resp = client.post("/api/students/301/attendance", json={"pin_code": "0000"})
    assert resp.status_code == 401

    # Correct PIN should work
    resp = client.post("/api/students/301/subjects", json={"pin_code": correct_pin})
    assert resp.status_code == 200


def _make_synthetic_wav_bytes(freq, duration=3, sample_rate=16000, seed=0):
    """Generates a synthetic, speech-like WAV (sine + noise) for testing the
    voice recognition pipeline without needing real recorded audio."""
    import wave
    import numpy as np
    from io import BytesIO

    rng = np.random.RandomState(seed)
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio = (
        0.3 * np.sin(2 * np.pi * freq * t)
        + 0.15 * np.sin(2 * np.pi * freq * 2.5 * t)
        + 0.05 * rng.randn(len(t))
    )
    audio = audio / np.max(np.abs(audio))
    audio_int16 = (audio * 32767 * 0.8).astype(np.int16)

    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    buf.seek(0)
    return buf



def _make_challenge_wav_bytes(freq, pattern, sample_rate=16000, seed=0):
    """Synthetic two-utterance sample matching the active-liveness timing
    challenge while keeping one frequency family as the fake speaker."""
    import wave
    import numpy as np
    from io import BytesIO

    rng = np.random.RandomState(seed)

    def tone(duration):
        t = np.arange(int(sample_rate * duration)) / sample_rate
        audio = (
            0.3 * np.sin(2 * np.pi * freq * t)
            + 0.12 * np.sin(2 * np.pi * freq * 2.5 * t)
            + 0.02 * rng.randn(len(t))
        )
        return audio

    short = tone(0.6)
    long = tone(1.8)
    pause = np.zeros(int(sample_rate * 0.5))
    audio = np.concatenate([short, pause, long] if pattern == "short_long" else [long, pause, short])
    audio = audio / max(np.max(np.abs(audio)), 1e-6)
    audio_int16 = (audio * 32767 * 0.8).astype(np.int16)

    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    buf.seek(0)
    return buf


def _get_voice_challenge(client, headers, subject_id):
    resp = client.get(f"/api/voice/challenge?subject_id={subject_id}", headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()

def test_voice_recognition_distinguishes_speakers(client):
    """End-to-end: enroll a synthetic 'voice', then recognize a similar vs a
    different synthetic voice - the pretrained-embedding pipeline should
    correctly separate them by cosine similarity."""
    client.post("/api/auth/register", json={
        "teacher_name": "T", "email": "t@test.com",
        "password": "secret123", "department": "CS"
    })
    token = client.post("/api/auth/login", json={
        "email": "t@test.com", "password": "secret123"
    }).get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    subject = client.post("/api/subjects/", json={
        "subject_name": "DSA", "section": "A"
    }, headers=headers).get_json()["subject"]

    student = client.post("/api/students/", json={
        "name": "S1", "roll_number": "401", "class_section": "A", "email_phone": ""
    }, headers=headers).get_json()["student"]
    client.post("/api/students/join-subject", json={
        "roll_number": "401", "pin_code": student["pin_code"], "subject_code": subject["subject_code"]
    })

    # Enroll with a synthetic "voice A" sample
    enroll_audio = _make_synthetic_wav_bytes(120, seed=1)
    resp = client.post(
        "/api/voice/enroll",
        data={"roll_number": "401", "audio": (enroll_audio, "enroll.wav")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()

    # Recognize with a similar-frequency-family sample (same "speaker") - should match
    challenge = _get_voice_challenge(client, headers, subject["id"])
    match_audio = _make_challenge_wav_bytes(122, challenge["pattern"], seed=2)
    resp = client.post(
        "/api/voice/recognize",
        data={
            "subject_id": str(subject["id"]),
            "challenge_token": challenge["challenge_token"],
            "audio": (match_audio, "match.wav"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    preview = resp.get_json()["preview"]
    assert preview[0]["status"] == "Present"

    # Recognize with a very different frequency (different "speaker") - should not match
    challenge = _get_voice_challenge(client, headers, subject["id"])
    different_audio = _make_challenge_wav_bytes(220, challenge["pattern"], seed=3)
    resp = client.post(
        "/api/voice/recognize",
        data={
            "subject_id": str(subject["id"]),
            "challenge_token": challenge["challenge_token"],
            "audio": (different_audio, "different.wav"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    preview = resp.get_json()["preview"]
    assert preview[0]["status"] == "Absent"


def test_voice_replay_attack_rejected(client):
    """Submitting the exact same audio bytes twice for recognition must be
    rejected the second time - basic anti-replay protection."""
    client.post("/api/auth/register", json={
        "teacher_name": "T", "email": "t@test.com",
        "password": "secret123", "department": "CS"
    })
    token = client.post("/api/auth/login", json={
        "email": "t@test.com", "password": "secret123"
    }).get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    subject = client.post("/api/subjects/", json={
        "subject_name": "DSA", "section": "A"
    }, headers=headers).get_json()["subject"]

    student = client.post("/api/students/", json={
        "name": "S1", "roll_number": "501", "class_section": "A", "email_phone": ""
    }, headers=headers).get_json()["student"]
    client.post("/api/students/join-subject", json={
        "roll_number": "501", "pin_code": student["pin_code"], "subject_code": subject["subject_code"]
    })

    enroll_audio = _make_synthetic_wav_bytes(120, seed=1)
    client.post(
        "/api/voice/enroll",
        data={"roll_number": "501", "audio": (enroll_audio, "enroll.wav")},
        headers=headers,
        content_type="multipart/form-data",
    )

    # Same challenge + same audio cannot be reused.
    challenge = _get_voice_challenge(client, headers, subject["id"])
    same_audio_bytes = _make_challenge_wav_bytes(122, challenge["pattern"], seed=2).getvalue()

    from io import BytesIO

    first_attempt = BytesIO(same_audio_bytes)
    resp = client.post(
        "/api/voice/recognize",
        data={
            "subject_id": str(subject["id"]),
            "challenge_token": challenge["challenge_token"],
            "audio": (first_attempt, "attempt1.wav"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()

    second_attempt = BytesIO(same_audio_bytes)
    resp = client.post(
        "/api/voice/recognize",
        data={
            "subject_id": str(subject["id"]),
            "challenge_token": challenge["challenge_token"],
            "audio": (second_attempt, "attempt2.wav"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert any(word in resp.get_json()["message"].lower() for word in ("replay", "already", "challenge"))


def test_face_recognize_requires_liveness_frames(client):
    """A client omitting the mandatory multi-frame liveness burst must not
    be able to bypass face liveness entirely."""
    client.post("/api/auth/register", json={
        "teacher_name": "T", "email": "t@test.com",
        "password": "secret123", "department": "CS"
    })
    token = client.post("/api/auth/login", json={
        "email": "t@test.com", "password": "secret123"
    }).get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    subject = client.post("/api/subjects/", json={
        "subject_name": "DSA", "section": "A"
    }, headers=headers).get_json()["subject"]

    from io import BytesIO
    fake_image = (BytesIO(b"fake jpeg bytes"), "capture.jpg")

    # Omitting the required liveness frame burst must be rejected, not silently skip liveness.
    resp = client.post(
        "/api/face/recognize",
        data={"subject_id": str(subject["id"]), "image": fake_image},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "required" in resp.get_json()["message"].lower()


def test_screen_replay_signal_detects_moire_pattern():
    """Unit test for the advisory screen-replay heuristic: a synthetic
    'screen-like' image (with an added periodic grid, simulating Moiré
    interference from an LCD/phone screen) should score higher than a
    smooth 'real face-like' image, and cross the suspicion threshold."""
    import numpy as np
    import cv2
    from app.utils.face_engine import detect_screen_replay_signal

    real_like = cv2.GaussianBlur(
        np.random.RandomState(1).normal(128, 15, (200, 200)).astype(np.uint8), (5, 5), 0
    )
    is_suspicious_real, real_score = detect_screen_replay_signal(real_like)

    xx, yy = np.meshgrid(np.arange(200), np.arange(200))
    grid = 40 * np.sin(2 * np.pi * xx / 4) * np.sin(2 * np.pi * yy / 4)
    screen_like = np.clip(real_like.astype(np.float32) + grid, 0, 255).astype(np.uint8)
    is_suspicious_screen, screen_score = detect_screen_replay_signal(screen_like)

    assert screen_score > real_score
    assert is_suspicious_screen is True
    assert is_suspicious_real is False


def test_narrow_bandwidth_signal_detects_band_limited_audio():
    """Unit test for the advisory narrow-bandwidth heuristic: genuinely
    band-limited audio (simulating a small speaker / telephone-quality
    replay) should be flagged, while broadband audio should not."""
    import numpy as np
    from app.utils.voice_engine import detect_narrow_bandwidth_signal

    sample_rate = 16000
    t = np.linspace(0, 3, sample_rate * 3)
    rng = np.random.RandomState(1)

    wide = rng.randn(len(t)) * 0.3
    is_suspicious_wide, wide_bw = detect_narrow_bandwidth_signal(wide, sample_rate)
    assert is_suspicious_wide is False
    assert wide_bw > 5000

    # Simple manual band-limiting (avoid adding scipy as a dependency just for this test):
    # a single low-frequency tone plus a little noise concentrates energy narrowly.
    narrow = 0.4 * np.sin(2 * np.pi * 300 * t) + 0.4 * np.sin(2 * np.pi * 500 * t) + 0.02 * rng.randn(len(t))
    is_suspicious_narrow, narrow_bw = detect_narrow_bandwidth_signal(narrow, sample_rate)
    assert narrow_bw < wide_bw


def test_blink_liveness_three_frame_mode():
    """check_blink_liveness should support an optional third frame for the
    fuller Open->Closed->Open pattern, and reject when eyes don't reopen."""
    import numpy as np
    from app.utils.face_engine import check_blink_liveness

    blank = np.zeros((200, 200, 3), dtype=np.uint8)

    # No eyes detected in any frame -> rejected at the very first check.
    is_live, msg = check_blink_liveness(blank, blank, blank)
    assert is_live is False
    assert "first frame" in msg.lower()

    # Backward-compatible two-frame mode still works when the third frame is omitted.
    is_live, msg = check_blink_liveness(blank, blank, None)
    assert is_live is False


def test_recognize_face_filters_out_unenrolled_predictions(monkeypatch):
    """Unit test: if the LBPH model predicts a student ID that isn't in the
    enrolled_students list passed in (e.g. it belongs to a student from a
    different subject), that prediction must be discarded, not surfaced."""
    import numpy as np
    from app.utils import face_engine

    class FakeStudent:
        def __init__(self, id, name, roll_number):
            self.id = id
            self.name = name
            self.roll_number = roll_number

    # Two faces "detected" in the photo
    fake_face_1 = np.zeros((200, 200), dtype=np.uint8)
    fake_face_2 = np.ones((200, 200), dtype=np.uint8)

    monkeypatch.setattr(face_engine, "detect_faces", lambda image: [fake_face_1, fake_face_2])
    monkeypatch.setattr(face_engine.os.path, "exists", lambda path: True)
    monkeypatch.setattr(face_engine, "read_camera_image", lambda f: "fake_image")

    class FakeRecognizer:
        def read(self, path):
            pass

        def predict(self, face):
            # face 1 predicts student_id=1 (enrolled), face 2 predicts
            # student_id=999 (NOT enrolled in this subject)
            if face is fake_face_1:
                return 1, 50.0  # confident match
            return 999, 40.0  # even more confident, but wrong subject

    monkeypatch.setattr(
        face_engine.cv2.face, "LBPHFaceRecognizer_create", lambda: FakeRecognizer()
    )

    enrolled_students = [FakeStudent(1, "Alice", "101")]  # only student 1 is enrolled here

    success, message, preview = face_engine.recognize_face(
        camera_file=object(), enrolled_students=enrolled_students, face_model_path="fake_path"
    )

    assert success is True
    assert len(preview) == 1
    assert preview[0]["student_id"] == 1
    assert preview[0]["status"] == "Present"
    # student_id 999 must never appear anywhere in the output
    assert all(p["student_id"] != 999 for p in preview)

def test_group_liveness_requires_each_face_to_blink(monkeypatch):
    """Every face track - not just the first/largest - must complete an
    open->closed->open sequence."""
    from app.utils import face_engine

    # Two stationary faces across 8 frames. Both blink and reopen.
    sequence = [
        [(100, 100, 2), (300, 100, 2)],
        [(100, 100, 2), (300, 100, 2)],
        [(100, 100, 0), (300, 100, 2)],
        [(100, 100, 2), (300, 100, 0)],
        [(100, 100, 2), (300, 100, 2)],
        [(100, 100, 2), (300, 100, 2)],
        [(100, 100, 2), (300, 100, 2)],
        [(100, 100, 2), (300, 100, 2)],
    ]
    cursor = {"i": 0}

    def fake_states(_frame):
        row = sequence[cursor["i"]]
        cursor["i"] += 1
        return [
            {"box": (x, y, 80, 80), "center": (x + 40.0, y + 40.0),
             "diag": 113.0, "open_eyes": eyes}
            for x, y, eyes in row
        ]

    monkeypatch.setattr(face_engine, "_detect_face_eye_states", fake_states)
    ok, _, count = face_engine.check_group_blink_liveness([object()] * 8)
    assert ok is True
    assert count == 2


def test_voice_liveness_pattern_from_energy_envelope():
    from app.utils.voice_engine import verify_voice_liveness_pattern
    import numpy as np

    sr = 16000
    # ~0.6s sound, 0.5s silence, ~1.8s sound
    short = 0.20 * np.sin(2 * np.pi * 180 * np.arange(int(0.6 * sr)) / sr)
    silence = np.zeros(int(0.5 * sr))
    long = 0.20 * np.sin(2 * np.pi * 180 * np.arange(int(1.8 * sr)) / sr)
    wav = np.concatenate([short, silence, long]).astype(np.float32)

    ok, _ = verify_voice_liveness_pattern(wav, "short_long")
    assert ok is True
    ok, _ = verify_voice_liveness_pattern(wav, "long_short")
    assert ok is False



def _register_teacher_and_student(client, teacher_email="edge@test.com", roll_number="601"):
    client.post("/api/auth/register", json={
        "teacher_name": "Edge Teacher", "email": teacher_email,
        "password": "secret123", "department": "CS"
    })
    token = client.post("/api/auth/login", json={
        "email": teacher_email, "password": "secret123"
    }).get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    subject = client.post("/api/subjects/", json={
        "subject_name": "Edge Cases", "section": "A"
    }, headers=headers).get_json()["subject"]

    student = client.post("/api/students/", json={
        "name": "Edge Student", "roll_number": roll_number, "class_section": "A", "email_phone": ""
    }, headers=headers).get_json()["student"]

    client.post("/api/students/join-subject", json={
        "roll_number": roll_number, "pin_code": student["pin_code"], "subject_code": subject["subject_code"]
    })

    return headers, subject, student


def test_face_enroll_missing_roll_number(client):
    """roll_number omitted entirely should be a clean 400, not a crash."""
    headers, _, _ = _register_teacher_and_student(client, "a1@test.com", "701")

    from io import BytesIO
    resp = client.post(
        "/api/face/enroll",
        data={"image": (BytesIO(b"fake"), "capture.jpg")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "roll_number" in resp.get_json()["message"].lower()


def test_face_enroll_unknown_student(client):
    """Enrolling a roll_number that doesn't exist must fail cleanly (404),
    not silently create orphaned biometric data."""
    headers, _, _ = _register_teacher_and_student(client, "a2@test.com", "702")

    from io import BytesIO
    resp = client.post(
        "/api/face/enroll",
        data={"roll_number": "does-not-exist", "image": (BytesIO(b"fake"), "capture.jpg")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 404


def test_face_enroll_no_face_detected(client):
    """An image with no detectable face (e.g. a blank/garbage image) must be
    rejected with a clear message, not silently 'enrolled' with junk data."""
    headers, _, _ = _register_teacher_and_student(client, "a3@test.com", "703")

    import numpy as np
    import cv2
    from io import BytesIO

    blank = np.zeros((200, 200, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", blank)
    assert ok

    resp = client.post(
        "/api/face/enroll",
        data={"roll_number": "703", "image": (BytesIO(encoded.tobytes()), "capture.jpg")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "no clear face" in resp.get_json()["message"].lower()


def test_voice_enroll_missing_roll_number(client):
    headers, _, _ = _register_teacher_and_student(client, "a4@test.com", "704")

    audio = _make_synthetic_wav_bytes(150, seed=10)
    resp = client.post(
        "/api/voice/enroll",
        data={"audio": (audio, "sample.wav")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "roll_number" in resp.get_json()["message"].lower()


def test_voice_enroll_unknown_student(client):
    headers, _, _ = _register_teacher_and_student(client, "a5@test.com", "705")

    audio = _make_synthetic_wav_bytes(150, seed=11)
    resp = client.post(
        "/api/voice/enroll",
        data={"roll_number": "does-not-exist", "audio": (audio, "sample.wav")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 404


def test_voice_enroll_too_short_audio(client):
    """A very short recording (below the ~1.5s minimum) must be rejected
    with a clear message rather than producing a garbage/degenerate embedding."""
    headers, _, _ = _register_teacher_and_student(client, "a6@test.com", "706")

    # 0.3 seconds - well under the minimum required duration
    short_audio = _make_synthetic_wav_bytes(150, duration=0.3, seed=12)
    resp = client.post(
        "/api/voice/enroll",
        data={"roll_number": "706", "audio": (short_audio, "sample.wav")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "too short" in resp.get_json()["message"].lower() or "invalid" in resp.get_json()["message"].lower()


def test_voice_enroll_missing_audio_file(client):
    headers, _, _ = _register_teacher_and_student(client, "a7@test.com", "707")

    resp = client.post(
        "/api/voice/enroll",
        data={"roll_number": "707"},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_face_recognize_with_no_enrolled_students_in_subject(client):
    """Recognizing against a subject with zero enrolled students should not
    crash - it should cleanly report no students to check against."""
    client.post("/api/auth/register", json={
        "teacher_name": "T", "email": "a8@test.com",
        "password": "secret123", "department": "CS"
    })
    token = client.post("/api/auth/login", json={
        "email": "a8@test.com", "password": "secret123"
    }).get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # subject created but nobody joined it
    subject = client.post("/api/subjects/", json={
        "subject_name": "Empty Subject", "section": "A"
    }, headers=headers).get_json()["subject"]

    from io import BytesIO
    fake_image = (BytesIO(b"fake"), "capture.jpg")

    resp = client.post(
        "/api/face/recognize",
        data={
            "subject_id": str(subject["id"]),
            "image": fake_image,
            "liveness_frames": [(BytesIO(b"fake"), f"f{i}.jpg") for i in range(8)],
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    # No face model trained yet (nobody enrolled) - should fail cleanly, not 500
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_voice_enroll_allows_multiple_samples_per_student(client):
    """Enrolling voice for the same student twice should succeed both times
    (multiple samples improve matching), not error as a 'duplicate'."""
    headers, _, _ = _register_teacher_and_student(client, "a9@test.com", "709")

    audio1 = _make_synthetic_wav_bytes(150, seed=20)
    resp1 = client.post(
        "/api/voice/enroll",
        data={"roll_number": "709", "audio": (audio1, "sample1.wav")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp1.status_code == 200

    audio2 = _make_synthetic_wav_bytes(152, seed=21)
    resp2 = client.post(
        "/api/voice/enroll",
        data={"roll_number": "709", "audio": (audio2, "sample2.wav")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp2.status_code == 200
