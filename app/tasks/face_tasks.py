from flask import current_app

from app.celery_app import celery


@celery.task(name="retrain_face_model_task")
def retrain_face_model_task():
    from app.utils.face_engine import retrain_face_model
    return retrain_face_model(current_app.config["FACE_MODEL_PATH"])
