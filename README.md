# Serenia Uptime

> **Reliable Monitoring. Continuous Availability.**

Serenia Uptime is a production-ready web application that keeps your websites alive by periodically pinging registered URLs every 3 minutes, tracking uptime, response times, and status codes — all from a clean, dark-mode-first dashboard.

---

## Features

- **Auto-ping** every 3 minutes (configurable)
- **Uptime percentage** calculated from check history
- **Response time tracking** with sparkline charts
- **Status badges** — Online / Offline / Unknown
- **CSV export** of full monitoring history
- **Dark & light mode** toggle
- **Search & filter** across monitored sites
- **Manual check** trigger per site
- **CSRF protection** & URL validation
- **PostgreSQL-ready** architecture (SQLite for local dev)

---

## Tech Stack

| Layer       | Technology                        |
|-------------|-----------------------------------|
| Backend     | Python 3.12, Flask, APScheduler   |
| ORM         | SQLAlchemy (SQLite / PostgreSQL)  |
| Frontend    | HTML5, CSS3, Vanilla JS           |
| Deployment  | Gunicorn, Render, GitHub          |

---

## Quick Start (local)

```bash
# 1. Clone the repository
git clone https://github.com/your-username/serenia-uptime.git
cd serenia-uptime

# 2. Create & activate a virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and set a strong SECRET_KEY

# 5. Run the app
python app.py
```

Open http://localhost:5000 in your browser.

---

## Deploying to Render

1. Push this repository to GitHub.
2. Sign in to [Render](https://render.com) and click **New → Blueprint**.
3. Connect your GitHub repo — Render reads `render.yaml` automatically.
4. A free PostgreSQL database and web service are provisioned.
5. Render sets `DATABASE_URL` and `SECRET_KEY` automatically.
6. Click **Apply** — your app is live in ~2 minutes.

---

## Environment Variables

| Variable       | Description                           | Default                    |
|----------------|---------------------------------------|----------------------------|
| `SECRET_KEY`   | Flask secret key (must be random)     | *dev placeholder*          |
| `DATABASE_URL` | SQLAlchemy DB URI                     | `sqlite:///instance/serenia.db` |
| `FLASK_DEBUG`  | Enable debug mode (`true`/`false`)    | `false`                    |
| `PORT`         | Port for local dev                    | `5000`                     |

---

## Project Structure

```
serenia-uptime/
├── app.py                  # Flask app factory + routes
├── requirements.txt
├── render.yaml             # Render deployment blueprint
├── Procfile
├── .gitignore
├── .env.example
├── models/
│   └── database.py         # SQLAlchemy models (Website, CheckHistory)
├── monitoring/
│   └── monitor.py          # APScheduler + check engine
├── static/
│   ├── css/style.css
│   └── js/app.js
├── templates/
│   ├── base.html
│   ├── landing.html        # Public landing page
│   ├── dashboard.html
│   ├── add_website.html
│   ├── analytics.html
│   ├── site_detail.html
│   └── error.html
└── instance/
    └── serenia.db          # SQLite (local only, git-ignored)
```

---

## Status Logic

| Result                   | Status  |
|--------------------------|---------|
| HTTP 200–399             | Online  |
| HTTP 400+                | Offline |
| Timeout / Connection err | Offline |

---

## License

MIT © 2025 Serenia Uptime
