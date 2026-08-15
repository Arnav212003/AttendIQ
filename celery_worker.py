from app import create_app
from app.celery_app import init_celery

flask_app = create_app()
celery = init_celery(flask_app)

# Registers tasks (import for side effect)
from app.tasks import face_tasks  # noqa: E402,F401
