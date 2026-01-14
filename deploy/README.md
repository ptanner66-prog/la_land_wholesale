# LA Land Wholesale - Production Deployment

This directory contains all files needed to deploy the LA Land Wholesale platform in a production environment.

## Quick Start

```bash
# 1. Copy environment template
cp .env.prod.example .env.prod

# 2. Edit .env.prod with real credentials
vim .env.prod

# 3. Build and start services
docker-compose -f docker-compose.prod.yml up -d --build

# 4. Check service health
curl http://localhost/health
```

## Architecture

```
                    ┌─────────────┐
                    │   Nginx     │
                    │ (Port 80)   │
                    └──────┬──────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │   API    │    │Dashboard │    │ Metrics  │
    │ (FastAPI)│    │(Streamlit)│   │ /metrics │
    │ Port 8000│    │ Port 8501│    │          │
    └────┬─────┘    └────┬─────┘    └──────────┘
         │               │
         └───────┬───────┘
                 │
         ┌───────▼───────┐
         │   PostgreSQL  │
         │   + PostGIS   │
         │   Port 5432   │
         └───────────────┘
```

## Services

### 1. API Server (`api`)
- FastAPI backend serving REST endpoints
- Handles lead management, scoring, outreach
- Health checks at `/health`, `/health/ready`, `/health/live`

### 2. Dashboard (`dashboard`)
- Streamlit web interface
- Accessible via nginx at `/dashboard`

### 3. Scheduler (`scheduler`)
- APScheduler-based background jobs
- Runs daily pipeline: ingestion → scoring → outreach

### 4. PostgreSQL with PostGIS (`db`)
- Database with spatial extensions
- Persistent volume for data

### 5. Nginx (`nginx`)
- Reverse proxy for all services
- SSL termination (configure in nginx.conf)

## Files

| File | Description |
|------|-------------|
| `Dockerfile` | Multi-stage build for Python app |
| `docker-compose.prod.yml` | Production compose file |
| `nginx.conf` | Nginx reverse proxy config |
| `.env.prod.example` | Environment template |
| `systemd/` | Systemd service files |
| `scripts/` | Deployment scripts |

## Environment Variables

See `.env.prod.example` for all required variables:

- `DATABASE_URL` - PostgreSQL connection string
- `OPENAI_API_KEY` - OpenAI API key
- `TWILIO_*` - Twilio credentials
- `DRY_RUN` - Set to `false` for production

## Scaling

```bash
# Scale API workers
docker-compose -f docker-compose.prod.yml up -d --scale api=3
```

## Logs

```bash
# View all logs
docker-compose -f docker-compose.prod.yml logs -f

# View specific service
docker-compose -f docker-compose.prod.yml logs -f api
```

## Backup

```bash
# Backup database
docker-compose -f docker-compose.prod.yml exec db pg_dump -U la_land la_land > backup.sql
```

## SSL/TLS

For production, configure SSL in `nginx.conf`:

```nginx
server {
    listen 443 ssl;
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    # ... rest of config
}
```
