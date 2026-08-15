#!/bin/sh
set -e

if [ "$SERVICE_ROLE" = "worker" ]; then
    echo "Starting Celery worker..."
    exec celery -A celery_worker.celery worker --loglevel=info
else
    echo "Starting web service..."
    flask db upgrade
    exec gunicorn -w 2 -b 0.0.0.0:${PORT:-5000} wsgi:app
fi