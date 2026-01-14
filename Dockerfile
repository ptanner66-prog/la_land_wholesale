# ==============================================================================
# LA Land Wholesale - Production Dockerfile
# Hybrid Python FastAPI + Node.js frontend application
# ==============================================================================

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies and Node.js
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Verify installations
RUN python --version && node --version && npm --version

# Copy dependency files first (for layer caching)
COPY requirements.txt .
COPY frontend/package.json frontend/package-lock.json* ./frontend/

# Copy all application code
COPY . .

# Make build script executable and run it
# build.sh will handle: pip install, npm ci, npm build, alembic migrations
RUN chmod +x build.sh && ./build.sh

# Expose port (Railway will set $PORT dynamically)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start command - Railway will inject $PORT
CMD uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT:-8000}
