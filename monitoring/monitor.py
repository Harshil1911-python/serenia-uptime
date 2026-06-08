"""
Serenia Uptime - Monitoring Engine
- Checks all registered websites every 3 minutes
- Sends Twilio SMS alert when a site goes offline
- Fetches latest GitHub commits for dev tracker
- All times in IST (UTC+5:30)
"""

import logging
import os
import time
from datetime import datetime, timezone, timedelta

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler       = BackgroundScheduler(timezone="Asia/Kolkata")
REQUEST_TIMEOUT = 15    # seconds
CHECK_INTERVAL  = 180   # seconds (3 minutes)
IST             = timezone(timedelta(hours=5, minutes=30))


def now_utc():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# SMS via Twilio
# ---------------------------------------------------------------------------

def send_sms_alert(site_name: str, url: str, status_code):
    """Send an SMS to all AlertContact numbers via Twilio."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token  = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_number = os.environ.get("TWILIO_FROM_NUMBER", "")

    if not all([account_sid, auth_token, from_number]):
        logger.warning("Twilio credentials not set — skipping SMS alert")
        return

    try:
        from models.database import AlertContact
        contacts = AlertContact.query.all()
        if not contacts:
            return

        ist_time = datetime.now(IST).strftime("%I:%M %p IST, %d %b %Y")
        body = (
            f"🔴 SERENIA ALERT\n"
            f"Site: {site_name}\n"
            f"URL: {url}\n"
            f"Status: OFFLINE{' (HTTP ' + str(status_code) + ')' if status_code else ''}\n"
            f"Time: {ist_time}\n"
            f"Check your dashboard immediately."
        )

        for contact in contacts:
            try:
                resp = requests.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
                    auth=(account_sid, auth_token),
                    data={
                        "From": from_number,
                        "To":   contact.phone,
                        "Body": body,
                    },
                    timeout=10,
                )
                if resp.status_code == 201:
                    logger.info("SMS alert sent to %s", contact.phone)
                else:
                    logger.error("Twilio error %s: %s", resp.status_code, resp.text[:200])
            except Exception as exc:
                logger.error("Failed to send SMS to %s: %s", contact.phone, exc)

    except Exception as exc:
        logger.error("send_sms_alert error: %s", exc)


# ---------------------------------------------------------------------------
# Single website check
# ---------------------------------------------------------------------------

def check_website(app, website_id: int):
    with app.app_context():
        from models.database import db, Website, CheckHistory

        website = Website.query.get(website_id)
        if not website:
            return

        prev_status = website.current_status
        start       = time.time()
        status        = "offline"
        response_time = None
        status_code   = None

        try:
            response = requests.get(
                website.url,
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": "Serenia-Uptime-Monitor/1.0"},
                allow_redirects=True,
            )
            elapsed       = (time.time() - start) * 1000
            response_time = round(elapsed, 2)
            status_code   = response.status_code
            status        = "online" if 200 <= status_code < 400 else "offline"

        except requests.exceptions.Timeout:
            logger.warning("Timeout: %s", website.url)
        except requests.exceptions.ConnectionError:
            logger.warning("Connection error: %s", website.url)
        except requests.exceptions.RequestException as exc:
            logger.error("Request error %s: %s", website.url, exc)

        # Save check record
        history = CheckHistory(
            website_id=website_id,
            timestamp=now_utc(),
            status=status,
            response_time=response_time,
            status_code=status_code,
        )
        db.session.add(history)

        # Update website snapshot
        website.last_checked   = now_utc()
        website.current_status = status
        website.response_time  = response_time
        website.status_code    = status_code
        db.session.commit()

        logger.info("Checked %s → %s (%s ms)", website.url, status, response_time)

        # Send SMS alert if site just went offline
        if status == "offline" and prev_status != "offline":
            try:
                send_sms_alert(website.website_name, website.url, status_code)
            except Exception as exc:
                logger.error("SMS alert error: %s", exc)


# ---------------------------------------------------------------------------
# Check all websites
# ---------------------------------------------------------------------------

def check_all_websites(app):
    with app.app_context():
        from models.database import Website
        sites = Website.query.all()
        logger.info("Scheduled check for %d site(s)", len(sites))
        for site in sites:
            try:
                check_website(app, site.id)
            except Exception as exc:
                logger.error("Error checking site %d: %s", site.id, exc)


# ---------------------------------------------------------------------------
# GitHub commit fetcher
# ---------------------------------------------------------------------------

def fetch_commits(app):
    """Fetch latest commits from GitHub repo and store in DB."""
    repo  = os.environ.get("GITHUB_REPO", "")   # e.g. "username/serenia-uptime"
    token = os.environ.get("GITHUB_TOKEN", "")   # personal access token (optional)

    if not repo:
        return

    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        resp = requests.get(
            f"https://api.github.com/repos/{repo}/commits?per_page=20",
            headers=headers,
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("GitHub API %s: %s", resp.status_code, resp.text[:100])
            return

        with app.app_context():
            from models.database import db, Commit
            for item in resp.json():
                sha = item["sha"]
                if Commit.query.filter_by(sha=sha).first():
                    continue
                committed_str = item["commit"]["committer"]["date"]
                committed_at  = datetime.fromisoformat(committed_str.replace("Z", "+00:00"))
                c = Commit(
                    sha=sha,
                    message=item["commit"]["message"].split("\n")[0][:500],
                    author=item["commit"]["author"]["name"],
                    committed_at=committed_at,
                )
                db.session.add(c)
            db.session.commit()
            logger.info("Commits synced from GitHub")

    except Exception as exc:
        logger.error("fetch_commits error: %s", exc)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

def start_scheduler(app):
    if scheduler.running:
        return

    scheduler.add_job(
        func=check_all_websites,
        trigger=IntervalTrigger(seconds=CHECK_INTERVAL),
        id="monitor_all",
        name="Check all websites",
        replace_existing=True,
        args=[app],
    )

    # Fetch commits every 10 minutes
    scheduler.add_job(
        func=fetch_commits,
        trigger=IntervalTrigger(minutes=10),
        id="fetch_commits",
        name="Fetch GitHub commits",
        replace_existing=True,
        args=[app],
    )

    scheduler.start()

    # Run immediately on startup
    try:
        fetch_commits(app)
    except Exception:
        pass

    logger.info("Scheduler started (check=%ds, commit-sync=10min)", CHECK_INTERVAL)


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
