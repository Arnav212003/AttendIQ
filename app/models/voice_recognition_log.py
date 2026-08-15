from datetime import datetime, timezone

from app.extensions import db


class VoiceRecognitionLog(db.Model):
    """Replay/liveness audit record for voice recognition.

    Stores the exact audio hash plus the one-time signed challenge nonce.
    Either repeating the same recording or reusing a consumed challenge is
    rejected before attendance is accepted.
    """

    __tablename__ = "voice_recognition_logs"

    id = db.Column(db.Integer, primary_key=True)
    audio_hash = db.Column(db.String(64), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    # Signed active-liveness challenge nonce. Unique when present so a valid
    # challenge token cannot be replayed with a newly re-recorded audio file.
    challenge_nonce = db.Column(db.String(32), nullable=True, unique=True, index=True)
    submitted_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
