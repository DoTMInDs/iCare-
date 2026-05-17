#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input

python manage.py makemigrations --noinput
python manage.py migrate --noinput || python manage.py migrate webpush --fake

# Auto-create superuser from environment variables (safe to run every deploy)
python manage.py create_superuser_env
