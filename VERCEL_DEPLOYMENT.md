# 🚀 Vercel Deployment Guide

## ✅ Frontend is NOW Vercel-Ready!

I've configured your app for Vercel deployment. Here's how to get it live in **under 5 minutes**.

---

## 🎯 **Strategy: Split Deployment**

```
Frontend (React/Vite)  →  Vercel (FREE)
Backend (FastAPI)      →  Railway ($5/mo) or Render (FREE)
```

**Why this works:**
- Vercel = Perfect for React (built by Vercel team)
- Railway/Render = Perfect for Python FastAPI
- Total cost: $0-5/month

---

## 📦 **Step 1: Deploy Frontend to Vercel (2 minutes)**

### **Option A: Vercel Dashboard (Easiest)**

1. **Go to**: https://vercel.com/new
2. **Import Git Repository**: Select `la_land_wholesale`
3. **Configure Project**:
   ```
   Framework Preset: Vite
   Root Directory: frontend
   Build Command: npm run build
   Output Directory: dist
   Install Command: npm install
   ```

4. **Environment Variables** (Add these):
   ```
   VITE_API_BASE_URL=https://your-backend.railway.app
   VITE_GOOGLE_MAPS_API_KEY=your-key-here (optional)
   ```

5. **Click Deploy!**

### **Option B: Vercel CLI (Fastest)**

```bash
# Install Vercel CLI
npm install -g vercel

# Login
vercel login

# Deploy from frontend directory
cd frontend
vercel

# Follow prompts:
# - Set root to ./frontend
# - Framework: Vite
# - Build command: npm run build
# - Output: dist

# Deploy to production
vercel --prod
```

**Your app will be live at**: `https://your-app.vercel.app`

---

## 🖥️ **Step 2: Deploy Backend** (Choose One)

### **Option 1: Railway.app** (RECOMMENDED - $5/month)

**Why Railway:**
- PostgreSQL database included
- Background tasks work
- WebSocket support
- Simple deployment

**Steps:**
```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login
railway login

# 3. Initialize project
railway init

# 4. Add PostgreSQL
railway add postgresql

# 5. Set environment variables
railway variables set OPENAI_API_KEY="sk-proj-..."
railway variables set USPS_USER_ID="55973273"
railway variables set TWILIO_ACCOUNT_SID="your-sid"
railway variables set TWILIO_AUTH_TOKEN="your-token"
railway variables set DRY_RUN="false"

# 6. Deploy!
railway up
```

**Railway will give you a URL**: `https://your-app.up.railway.app`

**Update frontend**: Go to Vercel dashboard → Settings → Environment Variables
```
VITE_API_BASE_URL=https://your-app.up.railway.app
```
Redeploy frontend (auto triggers on change)

---

### **Option 2: Render.com** (FREE tier available)

**Steps:**

1. **Go to**: https://render.com/
2. **New Web Service** → Connect GitHub
3. **Configure**:
   ```
   Name: la-land-api
   Environment: Python
   Build Command: pip install -r requirements.txt
   Start Command: uvicorn src.api.app:app --host 0.0.0.0 --port $PORT
   ```

4. **Environment Variables**:
   ```
   DATABASE_URL=<render-postgres-connection>
   OPENAI_API_KEY=sk-proj-...
   USPS_USER_ID=55973273
   TWILIO_ACCOUNT_SID=your-sid
   TWILIO_AUTH_TOKEN=your-token
   DRY_RUN=false
   ```

5. **Add PostgreSQL**: Dashboard → New → PostgreSQL

6. **Deploy!**

**Free tier limitations:**
- Spins down after 15 min inactivity
- Cold start takes ~30 seconds
- Good for testing, not production

---

### **Option 3: Fly.io** (FREE tier, always-on)

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Launch app
fly launch

# Follow prompts, select region

# Set secrets
fly secrets set OPENAI_API_KEY="sk-proj-..."
fly secrets set USPS_USER_ID="55973273"
fly secrets set DRY_RUN="false"

# Deploy
fly deploy
```

**Your API**: `https://your-app.fly.dev`

---

## 🔐 **Step 3: Update Frontend API URL**

After deploying backend, update Vercel:

1. **Vercel Dashboard** → Your Project → Settings
2. **Environment Variables** → Edit
3. **Update**:
   ```
   VITE_API_BASE_URL=https://your-backend-url.com
   ```
4. **Redeploy** (automatic on save)

---

## ✅ **Verification Checklist**

After deployment:

- [ ] Visit your Vercel URL: `https://your-app.vercel.app`
- [ ] Dashboard loads with dark theme
- [ ] Check API connection (should see data loading)
- [ ] Test backend: `https://your-backend/docs` (Swagger UI)
- [ ] Health check: `https://your-backend/detailed`

---

## 📊 **Cost Breakdown**

### **FREE Option** ($0/month)
```
✅ Vercel: Frontend hosting (FREE forever)
✅ Render: Backend + Database (FREE tier)
⚠️ Limitations: Backend sleeps after 15min
```

### **PRODUCTION Option** ($5/month)
```
✅ Vercel: Frontend (FREE forever)
✅ Railway: Backend + PostgreSQL ($5/month)
✅ Always-on, no cold starts
✅ Background tasks work
```

---

## 🔧 **Common Issues & Fixes**

### **Issue: "API connection failed"**
**Fix**: Check CORS settings in backend
```python
# src/api/app.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-app.vercel.app"],  # Update this!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### **Issue: "Environment variables not working"**
**Fix**: Vercel env vars must start with `VITE_`
```bash
✅ VITE_API_BASE_URL
❌ API_BASE_URL
```

### **Issue: "Backend builds but crashes"**
**Fix**: Check Python version
```bash
# Create runtime.txt in root:
python-3.11.0
```

---

## 🎯 **Next Steps After Deployment**

1. **Custom Domain** (Optional)
   - Buy domain from Namecheap/GoDaddy
   - Add to Vercel: Settings → Domains
   - Add to Railway: Settings → Custom Domain

2. **SSL Certificate**
   - ✅ Vercel includes FREE SSL (auto)
   - ✅ Railway includes FREE SSL (auto)

3. **Monitoring**
   - Add Sentry for error tracking
   - Use Vercel Analytics (built-in)
   - Railway provides logs and metrics

4. **CI/CD** (Auto-deploy on git push)
   - ✅ Vercel: Already set up!
   - ✅ Railway: Already set up!

---

## 📱 **Mobile-Responsive**

Your app is already mobile-responsive thanks to Tailwind CSS. Test on:
- Vercel provides preview URLs for every git push
- Test on your phone: just visit the Vercel URL

---

## 🚀 **Quick Deploy Summary**

**Total Time: ~10 minutes**

```bash
# 1. Deploy Frontend (2 min)
vercel --prod

# 2. Deploy Backend (5 min)
railway up

# 3. Connect them (1 min)
# Update VITE_API_BASE_URL in Vercel dashboard

# 4. Done! 🎉
```

---

## 📞 **Support Resources**

**Vercel Docs**: https://vercel.com/docs
**Railway Docs**: https://docs.railway.app
**Render Docs**: https://render.com/docs

**Your Vercel Config**: `vercel.json` (already created ✅)

---

## 🎉 **You're Ready!**

Your app is configured for Vercel. Just run:
```bash
cd frontend && vercel --prod
```

Then deploy backend to Railway/Render, connect them, and you're LIVE! 🚀
