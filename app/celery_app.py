import os
from celery import Celery


CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

celery = Celery("attendance_ai", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)


def init_celery(flask_app):
    """Wraps Celery tasks so they run inside a Flask app context (DB access etc.)."""

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery
