# Morty69 Services (Python)

Online store with cart, order tracking, admin panel, and Discord notifications. Built for **Python 3** on [Render](https://render.com).

## Deploy on Render

1. Push this repo to GitHub
2. Render Dashboard → your service → **Settings**
3. **Runtime:** Python 3
4. **Build Command:** `pip install -r requirements.txt`
5. **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
6. **Env vars:** `ADMIN_KEY=Morty666`, `DISCORD_WEBHOOK=your_webhook_url`
7. **Disk:** mount `/opt/render/project/src/data` (1 GB)
8. Manual Deploy

## Admin

Admin tab → key: `Morty666`

## Tech

- Python 3 + Flask
- SQLite (built-in, no npm issues)
- Gunicorn for production
