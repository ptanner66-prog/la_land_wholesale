#!/bin/bash
# =============================================================================
# Railway Startup Script - LA Land Wholesale
# Runs database migrations if DATABASE_URL is set, then starts the app
# =============================================================================

echo "==> Starting LA Land Wholesale..."

# Run database migrations if DATABASE_URL is set
if [ -n "$DATABASE_URL" ]; then
    echo "==> DATABASE_URL detected, running migrations..."
    alembic upgrade head || echo "WARNING: Migration failed, continuing anyway..."
else
    echo "==> No DATABASE_URL set, skipping migrations"
fi

echo "==> Starting uvicorn server..."
exec uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT:-8000}
