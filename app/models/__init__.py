from app.models.teacher import Teacher
from app.models.student import Student
from app.models.subject import Subject
from app.models.enrollment import Enrollment
from app.models.attendance import Attendance
from app.models.face_embedding import FaceEmbedding
from app.models.voice_embedding import VoiceEmbedding
from app.models.voice_recognition_log import VoiceRecognitionLog

__all__ = [
    "Teacher",
    "Student",
    "Subject",
    "Enrollment",
    "Attendance",
    "FaceEmbedding",
    "VoiceEmbedding",
    "VoiceRecognitionLog",
]
