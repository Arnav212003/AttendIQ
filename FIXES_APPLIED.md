# AttendIQ - Final Fixes Applied

This corrected build is based on the uploaded SmartAttendanceAI_Flask (14) project.

- Classroom face liveness now uses a ~3-second multi-frame burst and tracks every face present in the first frame. Each tracked face must complete an Open -> Closed -> Open blink before recognition proceeds.
- Voice recognition now requires a signed, short-lived randomized active-liveness timing challenge (short/pause/long or long/pause/short) before speaker-embedding matching.
- Voice challenge nonces are one-time use and persisted in replay logs; exact-audio SHA-256 replay detection remains as a second signal.
- Added a safe Alembic migration for the voice challenge nonce.
- Face recognition keeps predictions restricted to students enrolled in the selected subject.
- Evaluation scripts correctly label real vs synthetic runs.
- Face FAR/FRR evaluation was redesigned as open-set leave-one-identity-out evaluation so unknown identities are genuine impostor trials.
- Test-generated biometric files no longer pollute the repository; tests use temporary upload directories and runtime uploads are git-ignored.
- Render Docker deployment retains Redis, Celery worker, PostgreSQL, and FFmpeg support.

## Important evaluation limitation

Real-world biometric accuracy is intentionally **not fabricated**. The committed voice report remains clearly synthetic unless a labeled human voice dataset is supplied. The corrected face report no longer publishes the old misleading synthetic FAR/FRR table; run the new open-set script with labeled human face crops to obtain genuine face metrics.
