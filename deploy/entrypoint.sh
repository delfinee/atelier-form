#!/bin/sh
set -eu
python -m django check --deploy --fail-level ERROR
python -m django migrate --noinput
python -m django createcachetable
python -m django collectstatic --noinput
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 4 --timeout 60 --forwarded-allow-ips='*' --error-logfile -
