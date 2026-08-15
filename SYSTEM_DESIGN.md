# AttendIQ — System Design

## Why this architecture
Old version used Streamlit + flat CSV files as a "database" — no auth security, no
transactional integrity, id-collision bugs, and the face model was retrained
synchronously on every single enrollment request. This rewrite fixes all of that
with a layered Flask backend.

## Layers
```
Client (mobile/web/Postman)
        │  REST + JWT
        ▼
Routes (Blueprints)      → HTTP concerns only: parse request, call service, format response
        ▼
Services                 → business rules, validation
        ▼
Models (SQLAlchemy ORM)  → schema, relationships, constraints
        ▼
PostgreSQL               → source of truth
        │
        └── Celery worker (Redis broker) → async face-model retraining
```

## Key fixes vs the old system
| Problem (old) | Fix (new) |
|---|---|
| `id = len(df) + 1` → duplicate IDs possible | DB auto-increment primary keys |
| Plaintext passwords in CSV | `werkzeug.security` password hashing |
| No transactional writes → race conditions | PostgreSQL transactions + unique constraints (`date+subject+student`, `student+subject` for enrollment) |
| Face model retrained synchronously (blocks request, O(n) every enrollment) | Celery task queue — retraining happens in background worker |
| No auth on API | JWT (Flask-JWT-Extended), role field for RBAC |
| No rate limiting | Flask-Limiter on auth endpoints |

## Database Schema (simplified ER)
```
Teacher 1───* Subject 1───* Enrollment *───1 Student
                  │                              │
                  └──────* Attendance *───────────┘
Student 1───* FaceEmbedding
Student 1───* VoiceEmbedding
```

## Deployment
- `docker-compose up` spins up: Flask app (gunicorn), Celery worker, PostgreSQL, Redis.
- `wsgi.py` — production entrypoint. `run.py` — local dev entrypoint.
- `render.yaml` deploys all four pieces on Render.com as a Blueprint:
  `attendiq-web` and `attendiq-celery-worker` both build from the project's
  `Dockerfile` (env: docker, not Render's native Python buildpack) - this is
  deliberate: the native buildpack does not include `ffmpeg`, which `pydub`
  needs to decode browser-recorded audio (webm/ogg) for voice enrollment and
  recognition. Building from the Dockerfile guarantees `ffmpeg` is present in
  both services, same as local Docker Compose. Also included: `attendiq-redis`
  (Celery broker + rate-limit storage) and `attendiq-db` (PostgreSQL). Deploy
  via Render dashboard → New → Blueprint → select this repo.

## Frontend
Server-rendered pages (Jinja2 templates + vanilla JS calling the REST API) live under
`app/templates/`. This is intentionally a hybrid: the backend is a real REST API
(`/api/...`), and the frontend is a thin client consuming it — same pattern used by
mobile apps or a future React frontend.

- `/` — role selection
- `/login`, `/register` — teacher auth
- `/dashboard` — teacher: manage subjects, students, take attendance, view records
- `/student-portal` — student: join subject, view own subjects/attendance (no login needed)

## Known limitations (honest scope statement)
- **Face liveness**: two-frame blink check (REQUIRED, not optional, at the
  API level) is the hard gate - defeats a static printed photo. In addition,
  an advisory (non-blocking) Moiré-pattern/FFT signal flags likely
  screen-replay attempts (someone holding up a phone/laptop showing the
  enrolled person's face) for the teacher to review - see
  `detect_screen_replay_signal()`. This is deliberately advisory rather than
  a hard reject: it was validated only on synthetic test patterns and its
  real-world false-positive rate (e.g. from glasses reflections, textured
  hair) is unknown; auto-rejecting on an unvalidated signal risks locking out
  legitimate students. Neither check defeats a video replay of the enrolled
  person blinking, or a determined attacker scripting crafted frames directly
  against the API. True production-grade anti-spoofing would need a trained
  classifier (e.g. Silent-Face-Anti-Spoofing) or depth sensing - not implemented.
- **Voice anti-replay**: SHA-256 hash of submitted audio bytes rejects exact
  file resubmission (hard block). An advisory (non-blocking) narrow-bandwidth
  signal flags audio with unusually concentrated frequency content, which can
  indicate small-speaker playback - see `detect_narrow_bandwidth_signal()`.
  Also advisory rather than a hard reject, for the same reason as above (a
  real recording on a cheap mic or in a noisy room can look narrow-band with
  no spoofing involved). Neither check detects a stolen recording played
  through a speaker and re-captured with a genuinely wideband mic - true
  audio liveness would need device/channel fingerprinting or a live spoken
  challenge phrase verified via speech-to-text - not implemented.
- **Voice/face accuracy metrics**: `scripts/evaluate_voice_accuracy.py` and
  `scripts/evaluate_face_accuracy.py` default to synthetic data (sine-wave
  audio / textured patches) because no labeled dataset ships with this repo.
  **To get real numbers**: pass `--real-data-dir <path>` pointing at a folder
  structured as `<path>/<person_name>/<sample_file>` (one subfolder per
  person, several samples each) - the scripts will use real recordings/photos
  instead and label the report accordingly. Real evaluation is possible right
  now, it just requires collecting sample data first.

## Resume-worthy talking points
- Designed a layered REST API (Flask, Blueprints, service/repository separation).
- Moved a synchronous ML retraining bottleneck to an async Celery job queue.
- Modeled relational schema with unique constraints to eliminate a race-condition
  class of bugs present in the file-based predecessor.
- Containerized multi-service architecture (web / worker / db / cache) with Docker Compose.
- Built a JWT-authenticated frontend client on top of the API, matching how a
  mobile app or SPA would consume the same backend.

## Biometric liveness (current implementation)

- **Face:** the teacher dashboard captures a ~3-second burst of frames. The backend tracks every face present in the first frame and requires an Open -> Closed -> Open blink for each tracked face before classroom recognition proceeds. A frequency-domain screen-replay heuristic is advisory only because it has not been validated on a real spoofing dataset.
- **Voice:** every recognition attempt starts with a short-lived signed random timing challenge (`short -> pause -> long` or `long -> pause -> short`). The backend verifies the speech-energy pattern before speaker embedding comparison. Exact-file SHA-256 replay detection remains as a second signal, and narrow-band audio is surfaced as an advisory warning.
- These are **basic, explainable student-project liveness controls**, not production biometric PAD (presentation-attack-detection) certification.

## Evaluation data

The evaluation scripts support `--real-data-dir` for both voice and face data and now label real-data reports correctly. The committed `EVALUATION.md` must only be described as real-world performance if it was actually generated from labeled human recordings/photos; synthetic results are pipeline sanity checks, not accuracy claims.
