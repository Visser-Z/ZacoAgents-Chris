#!/bin/sh
# Migrations run before the app starts, in both targets, so there is never a version of the
# schema that only one environment has seen.
set -e

echo "Applying migrations..."
alembic upgrade head

exec "$@"
