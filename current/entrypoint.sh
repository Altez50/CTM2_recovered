#!/bin/bash
set -e

echo "Starting deployment script..."

DB_TYPE=$(awk -F= '
  /^\[Database\]/ { in_db=1; next }
  /^\[/ { in_db=0 }
  in_db && $1 ~ /^[[:space:]]*type[[:space:]]*$/ {
    value=$2
    gsub(/[[:space:]]/, "", value)
    print tolower(value)
    exit
  }
' env.ini 2>/dev/null || true)

# Wait for database
python wait_for_db.py

if [ "${DB_TYPE:-sqlite}" = "sqlite" ]; then
    echo "SQLite detected, skipping Alembic migrations."
else
    echo "Running database migrations..."
    alembic upgrade head
fi

# Start application
echo "Starting application..."
exec "$@"
