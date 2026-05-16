#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input

python manage.py migrate

if [ "$DJANGO_CREATEUSER" == "1" ]; then 
    python manage.py createsuperuser --noinput
fi

# python yedulo/manage.py runserver 0.0.0.0:$PORT
# python -m gunicorn yedulo/yedulo.asgi:application -k uvicorn.workers.UvicornWorker




