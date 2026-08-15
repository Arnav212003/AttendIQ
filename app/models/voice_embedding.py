import json
from datetime import datetime, timezone

from app.extensions import db


class VoiceEmbedding(db.Model):
    __tablename__ = "voice_embeddings"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    audio_path = db.Column(db.String(255), nullable=False)

    # 256-dim speaker embedding from a pretrained model (Resemblyzer), stored
    # as a JSON-encoded list of floats. Replaces the earlier handcrafted
    # duration/RMS/ZCR/spectral features with a proper learned representation.
    embedding_json = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_embedding(self, embedding_array):
        self.embedding_json = json.dumps(embedding_array.tolist())

    def get_embedding(self):
        import numpy as np
        return np.array(json.loads(self.embedding_json), dtype=np.float32)
