web: flask --app manage db upgrade && gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 2 --timeout 120 --access-logfile - app:app
worker: celery -A tasks.celery_app worker --loglevel=info --concurrency=2
