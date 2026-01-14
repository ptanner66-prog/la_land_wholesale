# ⚠️ IMPORTANT: Backend Deployment Guide

## 🚨 Why This App Won't Work Fully on Vercel

Your FastAPI backend at `src/api/app.py` includes:
- SQLite database (needs persistent filesystem)
- Background tasks and scheduled jobs
- Long-running operations (Vercel has 10s timeout)
- Twilio webhooks requiring always-on server

**Vercel serverless functions cannot support these requirements.**

---

## ✅ Current Vercel Setup (Frontend Only)

✅ **What's deployed on Vercel:**
- React dashboard (frontend)
- Static assets
- CDN distribution
- Auto HTTPS

❌ **What's NOT on Vercel:**
- Backend API (needs separate hosting)

---

## 🚀 Backend Deployment Options

### **Option 1: Railway.app** ($5/mo - RECOMMENDED)
```bash
# Install CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up

# Set environment variables
railway variables set DATABASE_URL="postgresql://..."
railway variables set OPENAI_API_KEY="sk-proj-..."
railway variables set USPS_USER_ID="55973273"
```

**Result:** `https://your-app.up.railway.app`

### **Option 2: Render.com** (FREE tier)
1. Go to https://render.com/
2. New Web Service → Connect GitHub
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn src.api.app:app --host 0.0.0.0 --port $PORT`

**Result:** `https://your-app.onrender.com`

### **Option 3: Fly.io** (FREE tier, always-on)
```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Deploy
fly launch
fly deploy
```

**Result:** `https://your-app.fly.dev`

---

## 🔗 Connecting Frontend to Backend

After deploying backend, update Vercel:

1. **Vercel Dashboard** → Your Project → Settings → Environment Variables
2. **Add/Update**:
   ```
   VITE_API_BASE_URL=https://your-backend.railway.app
   ```
3. **Redeploy** (automatic on env var change)

---

## 📊 Architecture

```
┌─────────────────────────────────────┐
│  Frontend (Vercel)                  │
│  https://your-app.vercel.app        │
│  ✅ Static React app                 │
│  ✅ CDN distributed                  │
│  ✅ FREE forever                     │
└─────────────────────────────────────┘
              ↓ API calls
┌─────────────────────────────────────┐
│  Backend (Railway/Render)           │
│  https://api.your-app.com           │
│  ✅ FastAPI + PostgreSQL             │
│  ✅ Background tasks                 │
│  ✅ Always-on server                 │
└─────────────────────────────────────┘
```

---

## ⚡ Quick Start

**Deploy Frontend (Vercel):**
```bash
# Already configured - just push to GitHub
git push origin main
# Vercel auto-deploys
```

**Deploy Backend (Railway):**
```bash
railway login
railway init
railway up
```

**Connect Them:**
```bash
# Update VITE_API_BASE_URL in Vercel dashboard
# Vercel will auto-redeploy
```

---

## 🎯 Current Status

✅ Frontend is Vercel-ready (configured correctly)
✅ `.vercelignore` excludes backend files
✅ `vercel.json` configured for Vite

⚠️ Backend needs separate hosting (see options above)

---

## 💡 Why Not Full-Stack Vercel?

Vercel's Python support uses serverless functions with:
- ❌ 10-second timeout (your app needs longer)
- ❌ No persistent filesystem (SQLite won't work)
- ❌ Cold starts (bad for webhooks)
- ❌ No background tasks

Railway/Render provide:
- ✅ Always-on server
- ✅ Persistent database
- ✅ No timeouts
- ✅ Background tasks work

---

## 📞 Need Help?

See `VERCEL_DEPLOYMENT.md` for full guide.
