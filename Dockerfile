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
# build.sh will handle: pip install, npm ci, npm build
RUN chmod +x build.sh && ./build.sh

# Make startup script executable
RUN chmod +x start.sh

# Expose port (Railway will set $PORT dynamically)
EXPOSE 8000

# Start command - runs migrations then starts uvicorn
CMD ["./start.sh"]
