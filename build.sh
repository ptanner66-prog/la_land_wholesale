#!/bin/bash
# =============================================================================
# Railway Build Script - LA Land Wholesale
# =============================================================================
set -e  # Exit on error

echo "==> Installing Python dependencies..."
pip install --no-cache-dir -r requirements.txt

echo "==> Checking if Node.js is available..."
if command -v node &> /dev/null; then
    echo "==> Node.js found: $(node --version)"
    echo "==> npm version: $(npm --version)"

    echo "==> Installing frontend dependencies..."
    cd frontend
    npm ci --production=false

    echo "==> Building frontend..."
    npm run build

    cd ..
    echo "==> Frontend build complete!"
else
    echo "==> Node.js not found - skipping frontend build"
fi

echo "==> Running database migrations..."
alembic upgrade head

echo "==> Build complete! Ready to start server."
