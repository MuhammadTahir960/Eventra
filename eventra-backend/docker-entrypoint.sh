#!/bin/sh
# Entrypoint for the `web` container.

set -e
python manage.py collectstatic --noinput
exec "$@"
