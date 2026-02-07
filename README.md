# Prediction Pool

A lightweight web app for predicting fight outcomes with friends. No accounts needed — just a name and a 4-digit PIN.

## Local Development

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

## Deploy to Railway

1. Push this code to a GitHub repository
2. Go to [railway.app](https://railway.app) and sign in with GitHub
3. Click "New Project" → "Deploy from GitHub Repo" → select your repo
4. Railway auto-detects Python and deploys. Done!

### Environment Variables (set in Railway dashboard)

- `SECRET_KEY` — any random string (Railway can auto-generate this)
- `DATABASE_URL` — if using PostgreSQL instead of SQLite

### Custom Domain

In Railway dashboard → your project → Settings → Custom Domain:
1. Add your domain (e.g., `pool.yourdomain.com`)
2. Railway gives you a CNAME target
3. In GoDaddy DNS, add a CNAME record pointing your subdomain to Railway's target
4. Wait for DNS propagation (usually 5–15 minutes)
