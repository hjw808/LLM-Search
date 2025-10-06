# Deployment Guide

## Option 1: Deploy to Railway (Recommended)

### Prerequisites
- Railway account (https://railway.app)
- GitHub account (for deployment from repo)

### Steps

1. **Push code to GitHub**
   ```bash
   cd ai-visibility-tester
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/yourusername/ai-visibility-tester.git
   git push -u origin main
   ```

2. **Create Railway Project**
   - Go to https://railway.app
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose `ai-visibility-tester` repository
   - Railway will auto-detect Python and deploy

3. **Add Environment Variables**
   In Railway dashboard, go to Variables tab and add:
   ```
   OPENAI_API_KEY=sk-...
   CLAUDE_API_KEY=sk-ant-...
   GEMINI_API_KEY=...
   DATABASE_URL=postgresql://...  (auto-generated if you add PostgreSQL service)
   ```

4. **Add PostgreSQL Database** (Optional but recommended)
   - In Railway dashboard, click "New"
   - Select "Database" → "PostgreSQL"
   - Railway will auto-generate DATABASE_URL
   - Database tables will be created automatically on first run

5. **Get your API URL**
   - In Railway dashboard, go to Settings → Networking
   - Click "Generate Domain"
   - Your API will be available at: `https://your-app.up.railway.app`

### Test the Deployment

```bash
curl https://your-app.up.railway.app/api/health
```

Should return:
```json
{
  "status": "healthy",
  "timestamp": "2025-01-06T10:00:00",
  "services": {
    "openai": true,
    "claude": true,
    "gemini": false
  }
}
```

---

## Option 2: Deploy to Render

### Prerequisites
- Render account (https://render.com)

### Steps

1. **Create new Web Service**
   - Go to https://render.com/dashboard
   - Click "New" → "Web Service"
   - Connect your GitHub repository

2. **Configure Service**
   ```
   Name: ai-visibility-api
   Environment: Python 3
   Build Command: pip install -r requirements.txt
   Start Command: cd api && uvicorn main:app --host 0.0.0.0 --port $PORT
   ```

3. **Add Environment Variables**
   Same as Railway (above)

4. **Add PostgreSQL Database**
   - Create new PostgreSQL database in Render
   - Copy connection string to DATABASE_URL

---

## Option 3: Local Development

### Run FastAPI Backend Locally

1. **Install dependencies**
   ```bash
   cd ai-visibility-tester
   pip install -r requirements.txt
   ```

2. **Set environment variables**
   Create `.env` file:
   ```
   OPENAI_API_KEY=sk-...
   CLAUDE_API_KEY=sk-ant-...
   GEMINI_API_KEY=...
   DATABASE_URL=sqlite:///./test_results.db
   ```

3. **Run the server**
   ```bash
   cd api
   uvicorn main:app --reload --port 8000
   ```

4. **Test locally**
   ```bash
   curl http://localhost:8000/api/health
   ```

---

## Next.js Frontend Configuration

After deploying the backend, update your Next.js frontend:

1. **Add environment variable** to Vercel or `.env.local`:
   ```
   NEXT_PUBLIC_BACKEND_URL=https://your-app.up.railway.app
   ```

2. **The frontend will automatically use this URL** for API calls

---

## Monitoring

### Health Check
```bash
curl https://your-app.up.railway.app/api/health
```

### View Logs (Railway)
- Go to Railway dashboard
- Click on your service
- View "Logs" tab

### View Database (Railway)
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Connect to database
railway connect postgresql
```

---

## Troubleshooting

### API returns 500 error
- Check environment variables are set correctly
- Check logs for error messages
- Verify DATABASE_URL format (must start with `postgresql://`)

### Tests timeout
- Increase timeout in Render/Railway settings
- Consider adding Redis for background task processing

### Database connection fails
- Verify DATABASE_URL is correct
- Check database service is running
- Ensure firewall allows connections

---

## Cost Estimate

### Railway
- Starter Plan: **$5/month**
- PostgreSQL: **$5/month**
- **Total: $10/month**

### Render
- Starter Instance: **$7/month**
- PostgreSQL: **$7/month**
- **Total: $14/month**

---

## Security Checklist

- [ ] Environment variables are set (not hardcoded)
- [ ] API keys are not committed to git
- [ ] CORS is configured correctly
- [ ] Database has backups enabled
- [ ] HTTPS is enabled (automatic on Railway/Render)
