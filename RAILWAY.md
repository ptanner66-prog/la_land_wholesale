# 🚀 Railway Deployment Guide - LA Land Wholesale

Deploy your fullstack application (FastAPI + React) to Railway in under 30 minutes.

## Prerequisites

- GitHub repository with your code
- Railway account (free tier available)
- API keys ready (OpenAI, USPS, Twilio, Google Maps)

---

## 🎯 Quick Deploy (5 Steps)

### 1. Install Railway CLI

```bash
npm i -g @railway/cli
```

### 2. Login and Initialize

```bash
railway login
railway init
```

**Select options:**
- Link to existing Railway project OR create new one
- Confirm GitHub repository connection

### 3. Add PostgreSQL Database

```bash
railway add -d postgres
```

Railway automatically sets `DATABASE_URL` environment variable.

### 4. Set Environment Variables

**Required:**
```bash
railway variables set OPENAI_API_KEY="sk-proj-YOUR-KEY-HERE"
railway variables set USPS_USER_ID="YOUR-USPS-CRID"
railway variables set DRY_RUN="true"
railway variables set ENVIRONMENT="production"
railway variables set LOG_LEVEL="INFO"
railway variables set LOG_FORMAT="json"
```

**Optional (Twilio SMS - add when ready):**
```bash
railway variables set TWILIO_ACCOUNT_SID="ACXXXXXXXX"
railway variables set TWILIO_AUTH_TOKEN="your-auth-token"
railway variables set TWILIO_PHONE_NUMBER="+15551234567"
```

**Optional (Google Maps):**
```bash
railway variables set GOOGLE_MAPS_API_KEY="AIzaSyXXXXXXXXX"
railway variables set VITE_GOOGLE_MAPS_API_KEY="AIzaSyXXXXXXXXX"
```

### 5. Deploy!

```bash
railway up
```

That's it! Railway will:
1. Run `build.sh` to install dependencies, build frontend, and run migrations
2. Start the FastAPI server with `uvicorn`
3. Serve React frontend from `/frontend/dist`
4. Assign you a public URL: `https://your-project.up.railway.app`

---

## 📋 What Happens During Deployment

### Build Phase (`build.sh`)
1. ✅ Install Python dependencies from `requirements.txt`
2. ✅ Install Node.js dependencies (`npm ci`)
3. ✅ Build React frontend (`npm run build` → `frontend/dist/`)
4. ✅ Run Alembic migrations (`alembic upgrade head`)

### Runtime Phase (`railway.toml`)
1. ✅ Start uvicorn server on Railway's `$PORT`
2. ✅ FastAPI serves API routes at `/api/*`, `/leads/*`, etc.
3. ✅ FastAPI serves React app for all other routes
4. ✅ Health check at `/` every 5 minutes

---

## 🔧 Configuration Files

| File | Purpose |
|------|---------|
| `railway.toml` | Railway build/deploy settings |
| `Procfile` | Backup start command |
| `build.sh` | Custom build script (frontend + migrations) |
| `requirements.txt` | Production Python dependencies |
| `requirements-dev.txt` | Development dependencies (excluded from Railway) |
| `.env.example` | Template for environment variables |

---

## 🌐 Accessing Your Application

After deployment:

- **Full Application**: `https://your-project.up.railway.app`
- **API Docs**: `https://your-project.up.railway.app/docs`
- **Health Check**: `https://your-project.up.railway.app/`
- **Leads Dashboard**: `https://your-project.up.railway.app/leads`

---

## 🐛 Troubleshooting

### Build Fails on Frontend Step
```bash
# Check Railway logs
railway logs

# Common fix: Ensure Node.js is available in Railway Nixpacks
# The build.sh script handles this automatically
```

### Database Migration Errors
```bash
# Connect to Railway shell
railway run bash

# Check database connection
psql $DATABASE_URL

# Manually run migrations
alembic upgrade head
```

### Application Won't Start
```bash
# Check logs
railway logs

# Verify environment variables
railway variables

# Ensure DATABASE_URL is set (should be automatic with postgres addon)
```

### Frontend Not Loading
- Check that `frontend/dist` exists after build
- Verify no TypeScript errors (build uses relaxed checking)
- Check browser console for API connection issues

---

## 🔄 Continuous Deployment

Railway automatically redeploys when you push to your connected GitHub branch:

```bash
git add .
git commit -m "Update application"
git push origin main
```

Railway detects the push and triggers a new deployment.

---

## 💰 Cost Estimate

**Free Tier Includes:**
- 500 hours of runtime/month
- PostgreSQL database (1GB storage)
- Automatic HTTPS
- Custom domains (optional)

**Your app will likely stay within free tier** during development/testing.

---

## 🎉 Success Checklist

- [ ] Railway CLI installed
- [ ] Logged in with `railway login`
- [ ] Project initialized with `railway init`
- [ ] PostgreSQL added with `railway add -d postgres`
- [ ] All environment variables set
- [ ] Deployed with `railway up`
- [ ] Application accessible at Railway URL
- [ ] API docs working at `/docs`
- [ ] Frontend dashboard loads
- [ ] Database migrations completed

---

## 📞 Next Steps

1. **Test the application**: Create leads, test outreach workflows
2. **Add custom domain**: `railway domain add yourdomain.com`
3. **Enable Twilio**: Set Twilio variables when ready for live SMS
4. **Disable DRY_RUN**: Set to `false` when ready for production
5. **Monitor logs**: Use `railway logs --follow` to watch activity

Need help? Check Railway docs at https://docs.railway.app
