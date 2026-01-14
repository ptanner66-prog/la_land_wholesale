#!/bin/bash
set -e  # Exit on any error

echo "==> Starting LA Land Wholesale..."

# ALWAYS run migrations - app has default database_url in config.py
echo "==> Running database migrations..."
alembic upgrade head

if [ $? -eq 0 ]; then
    echo "==> ✅ Migrations completed successfully"
else
    echo "==> ❌ ERROR: Migrations failed!"
    exit 1
fi

echo "==> Starting uvicorn server on port ${PORT:-8000}..."
exec uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT:-8000}
