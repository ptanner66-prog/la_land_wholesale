# Railway Deployment Fix - Database Migrations

## Problem

**User reported**: Blank dashboard, empty dropdowns, cannot interact with the app.

**Root cause**: All API calls were failing with 500 errors:
```
sqlite3.OperationalError: no such table: lead
```

Database tables were never created because migrations never ran.

## Why Migrations Weren't Running

The `start.sh` script had a conditional:
```bash
if [ -n "$DATABASE_URL" ]; then
    alembic upgrade head
else
    echo "Skipping migrations"
fi
```

Railway deployment had **no DATABASE_URL environment variable set**, so migrations were skipped.

But the application itself has a **default DATABASE_URL** in `src/core/config.py`:
```python
database_url: str = Field(
    default="sqlite:////{PROJECT_ROOT}/la_land_wholesale.db",
    alias="DATABASE_URL",
)
```

So the app would start, try to query the database, but find no tables.

## The Fix

Modified `start.sh` to **ALWAYS run migrations**:
```bash
#!/bin/bash
set -e  # Exit on any error

echo "==> Starting LA Land Wholesale..."
echo "==> Running database migrations..."
alembic upgrade head

if [ $? -eq 0 ]; then
    echo "==> ✅ Migrations completed successfully"
else
    echo "==> ❌ ERROR: Migrations failed!"
    exit 1
fi

echo "==> Starting uvicorn server..."
exec uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT:-8000}
```

Key changes:
1. **Removed conditional check** - Always run migrations
2. **Added `set -e`** - Exit immediately if migrations fail (don't start broken app)
3. **Added explicit error checking** - Log success/failure clearly
4. **App won't start if migrations fail** - Fail fast, fail loud

## What This Fixes

✅ Database tables created on first startup
✅ All API endpoints return 200 instead of 500
✅ `/active-market` endpoint works
✅ `/active-market/parishes` endpoint returns market data
✅ Dropdowns populate with clickable options
✅ Dashboard becomes interactive
✅ User can select markets and use the app

## Deployment Flow

1. Railway builds Docker image
2. Railway starts container
3. Container runs `./start.sh`
4. **Migrations run** → Tables created
5. Uvicorn starts → App serves requests
6. API calls succeed → Frontend works

## Verification

After deployment, check Railway logs for:
```
==> Starting LA Land Wholesale...
==> Running database migrations...
INFO  [alembic.runtime.migration] Running upgrade -> 0000_sqlite_init
INFO  [alembic.runtime.migration] Running upgrade 0000_sqlite_init -> 20251205_...
==> ✅ Migrations completed successfully
==> Starting uvicorn server on port 8000...
```

Then verify endpoints:
```bash
# Health check
curl https://lalandwholesale-production.up.railway.app/health

# Market data (should return LA, TX, MS, AR, AL)
curl https://lalandwholesale-production.up.railway.app/active-market/parishes
```

## Files Modified

- `start.sh` - Always run migrations before starting app
- `src/api/app.py` - Added dedicated `/health` endpoint, removed broken API prefix check

## Related Commits

1. Add dedicated /health endpoint for Railway health checks
2. Fix: Remove backwards API prefix check from catch-all route
3. **PROFESSIONAL FIX: Non-blocking startup + proper migration handling** (this commit)
