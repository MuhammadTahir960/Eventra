#!/bin/sh
# Entrypoint for the `web` container.

set -e

python -c "
import os, sys, time
import psycopg

deadline = time.monotonic() + 30
print('Waiting for database...')
while True:
    try:
        with psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=3):
            print('Database is available.')
            break
    except psycopg.OperationalError:
        if time.monotonic() >= deadline:
            print('Database not available after 30s. Giving up.', file=sys.stderr)
            sys.exit(1)
        time.sleep(1)
"
python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
