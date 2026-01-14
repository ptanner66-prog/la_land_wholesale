# 🔴 BLACK SCREEN FIX - Complete Solution

You merged the PR but still seeing a black screen. Here's the complete fix:

## Problem: Railway Missing Node.js

Railway's Nixpacks detected Python but **didn't install Node.js** to build your React frontend.

## Solution Just Pushed

I added `nixpacks.toml` which explicitly tells Railway to install:
- Python 3.11
- Node.js 20
- npm 9.x

**This ensures your frontend builds correctly.**

---

## 🚨 IMMEDIATE ACTION REQUIRED

Railway needs to redeploy with the new `nixpacks.toml` file. Follow these steps:

### Option 1: Force Railway Redeploy (Fastest - 2 minutes)

**In Railway Dashboard:**

1. Go to your project
2. Click **Deployments** tab
3. Click the **⋮** (three dots) menu on the latest deployment
4. Click **"Redeploy"** or **"Trigger Deploy"**
5. Wait 2-3 minutes

**OR via CLI:**
```bash
railway up --service your-service-name
```

### Option 2: Push Empty Commit to Trigger Rebuild

```bash
# Make sure you're on the branch Railway watches
git checkout main  # or claude/code-review-website-6fZUh

# Create empty commit to trigger Railway
git commit --allow-empty -m "Trigger Railway rebuild with nixpacks.toml"

# Push to trigger deployment
git push origin main  # or your Railway branch
```

### Option 3: Update Railway Branch Settings

If Railway isn't picking up changes:

1. Railway Dashboard → Your Project
2. **Settings** → **Source**
3. Verify **Branch** is set to: `claude/code-review-website-6fZUh` OR `main`
4. Click **"Deploy Now"**

---

## ✅ Verify in Railway Logs

After redeploying, check Railway logs for these SUCCESS indicators:

```
==> Node.js found: v20.x.x
==> npm version: 9.x.x
==> Installing frontend dependencies...
==> Building frontend...
✓ built in 9s
==> Frontend build complete!
```

If you see **"Node.js not found - skipping frontend build"**, the nixpacks.toml didn't apply.

---

## 🧪 Test After Deploy

Once Railway finishes deploying (2-3 minutes):

### 1. Hard Refresh Browser
```
Windows: Ctrl + Shift + R
Mac: Cmd + Shift + R
```

### 2. Check These URLs

**Root (Should show dashboard):**
```
https://your-project.railway.app/
```
Expected: Dark themed dashboard with navigation

**Health Check (Should show JSON):**
```
https://your-project.railway.app/health
```
Expected: `{"status":"healthy",...}`

**API Docs:**
```
https://your-project.railway.app/docs
```
Expected: Swagger UI documentation

### 3. Open Browser Console (F12)

Look for errors:
- **Red errors** about failed API calls? Share them with me
- **404s** for `/assets/*.js`? Frontend didn't build
- **CORS errors**? API client issue (already fixed)

---

## 🔍 Still Black Screen? Diagnostic Steps

### Check 1: Is Railway Building Frontend?

**Railway Dashboard → Deployments → Latest → View Logs**

Search logs for:
```
==> Building frontend...
✓ built in
```

**If MISSING:** nixpacks.toml didn't apply → try Option 2 above

### Check 2: Is Frontend Served?

Test this URL:
```
https://your-project.railway.app/assets/index-CB-B0iRB.js
```

**If 404:** Frontend didn't build or isn't being served
**If 200:** Frontend exists, issue is elsewhere

### Check 3: Browser Console Errors

Open **F12** → **Console** tab

Common errors and fixes:

**Error:** `Failed to load resource: net::ERR_CONNECTION_REFUSED`
- **Fix:** API client trying to call localhost → Already fixed in `client.ts`

**Error:** `Uncaught SyntaxError: Unexpected token '<'`
- **Fix:** API returning HTML instead of JSON → Check `api_prefixes` in `app.py`

**Error:** `Cannot read properties of undefined`
- **Fix:** React runtime error → Check browser console for stack trace

### Check 4: Railway Environment Variables

Railway Dashboard → Variables

**Required to be SET:**
- `DATABASE_URL` (auto-set by Railway when you add Postgres)
- `OPENAI_API_KEY`
- `ENVIRONMENT=production`
- `DRY_RUN=true`

**NOT required (uses defaults):**
- `VITE_API_BASE_URL` (defaults to empty string = relative URLs)

---

## 📋 Files Changed in Latest Push

1. **`nixpacks.toml`** (NEW) ← **CRITICAL FIX**
   - Tells Railway to install Node.js
   - Runs build.sh during install phase

2. **`frontend/src/api/client.ts`** (MODIFIED)
   - Uses relative URLs in production
   - Only uses localhost in development

3. **`src/api/routes/health.py`** (MODIFIED)
   - Health check moved to `/health`

4. **`src/api/app.py`** (MODIFIED)
   - Root `/` serves React dashboard
   - API routes excluded from frontend serving

5. **`railway.toml`** (MODIFIED)
   - Health check path updated to `/health`

---

## 🎯 Expected Result After Fix

**Before:**
```
Black screen OR:
{"status":"healthy","timestamp":"..."}
```

**After:**
```
┌─────────────────────────────────────┐
│  LA Land Wholesale Dashboard        │
│  [Dashboard] [Leads] [Buyers] ...   │
│                                     │
│  Welcome to your dashboard          │
│  No leads found - Get started       │
└─────────────────────────────────────┘
```

---

## 🆘 Emergency Fallback: Direct Railway Configuration

If nothing works, configure Railway manually:

### In Railway Dashboard:

1. **Settings** → **Build**
   - Build Command: `chmod +x build.sh && ./build.sh`
   - Install Command: (leave empty)

2. **Settings** → **Deploy**
   - Start Command: `uvicorn src.api.app:app --host 0.0.0.0 --port $PORT`
   - Health Check Path: `/health`

3. **Settings** → **Environment**
   - Add these if missing:
   ```
   NODE_VERSION=20
   NPM_VERSION=9
   ```

4. **Redeploy**

---

## 📞 Share This Info If Still Broken

If black screen persists after all fixes:

1. **Railway deployment URL:** `https://_____.railway.app`
2. **Browser console errors:** (screenshot or copy/paste)
3. **Railway build logs:** Last 50 lines from deployment
4. **What you see:** Blank black? JSON? Error message?

I need these 4 things to diagnose further.

---

## ✅ Confirmation Checklist

After deploying, confirm:

- [ ] Railway logs show "Node.js found"
- [ ] Railway logs show "Frontend build complete"
- [ ] Browser hard refresh (Ctrl+Shift+R)
- [ ] Dashboard loads at root URL
- [ ] No console errors (F12)
- [ ] API docs work at `/docs`

**All checked? Dashboard should be working! 🎉**
