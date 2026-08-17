# Morty69 Services

Online store with cart, order tracking, admin panel, and Discord notifications. Built for deployment on [Render](https://render.com).

## Features

- **Store** — Browse products with RBX and cash prices
- **Cart** — Add items, place orders, see waiting queue count
- **Check Order** — Look up order status with a unique code (e.g. `M69-AB12CD34`)
- **Admin** — Add/delete products (JPG upload), manage order status and estimated time
- **Discord** — New orders are sent to your webhook automatically

## Local Development

```bash
npm install
npm start
```

Open http://localhost:3000

## Deploy to Render

1. Push this repo to GitHub
2. Go to [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint**
3. Connect your GitHub repo — Render reads `render.yaml` automatically
4. Set environment variables:
   - `ADMIN_KEY` = `Morty666` (or your own key)
   - `DISCORD_WEBHOOK` = your Discord webhook URL
5. Deploy

The included persistent disk keeps your SQLite database across redeploys.

### Manual Deploy (without Blueprint)

1. **New Web Service** → connect GitHub repo
2. **Runtime:** Node
3. **Build Command:** `npm install`
4. **Start Command:** `npm start`
5. Add a **Persistent Disk** mounted at `/opt/render/project/src/data` (1 GB)
6. Add env vars: `ADMIN_KEY`, `DISCORD_WEBHOOK`

Product images and the database both live under `data/`, which is backed by the Render persistent disk.

## Admin Access

Go to the **Admin** tab and enter key: `Morty666` (or whatever you set in `ADMIN_KEY`).

## Order Statuses

| Status    | Meaning                          |
|-----------|----------------------------------|
| waiting   | In queue, not started yet        |
| pending   | Being worked on                  |
| completed | Order finished                   |

## Tech Stack

- Node.js + Express
- SQLite (better-sqlite3)
- Multer (JPG file uploads)
- Vanilla HTML/CSS/JS frontend
