# Railway Deployment Guide

## Deploy Backend + Database

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Create project and deploy
railway init
railway up

# Add PostgreSQL
railway add -d postgres

# Set environment variables
railway variables set OPENAI_API_KEY="sk-proj-s4TyrtL9FOK2OPgXG0afq4ck8SBSMPsAPtteUaawijyAmH3XNddCTCGiBLOmDOu9KyMUUZFp-syT3BIbkFJsL4SmgIkDRAaRu38mitnIU8ztxl-NYmDKAQNB0XncnHU48S5eyKRpOjeiEg9RegnoZn56yiMYA"
railway variables set USPS_USER_ID="55973273"
railway variables set DRY_RUN="true"
railway variables set ENVIRONMENT="production"
```

## Deploy Frontend (Separate Service)

```bash
# Create frontend service
railway service create frontend

# Set build config
railway variables set BUILD_COMMAND="cd frontend && npm install && npm run build"
railway variables set START_COMMAND="npx serve -s frontend/dist -l $PORT"
```

Or deploy frontend separately on Vercel/Netlify (recommended).

## Environment Variables Needed

- `DATABASE_URL` (auto-set by Railway when you add Postgres)
- `OPENAI_API_KEY`
- `USPS_USER_ID`
- `DRY_RUN=true`
- `TWILIO_*` (when ready)

## Your backend URL
https://your-project.up.railway.app
