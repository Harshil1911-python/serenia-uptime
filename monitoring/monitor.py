"""
Serenia Uptime - Monitoring Engine
Checks all registered websites every 3 minutes using APScheduler.
"""

import logging
import time
from datetime import datetime

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = BackgroundScheduler(timezone="UTC")

REQUEST_TIMEOUT = 15   # seconds
CHECK_INTERVAL  = 180  # seconds (3 minutes)


def check_website(app, website_id: int):
    """
    Perform a single GET request against the given website and store the result.
    Called by the scheduler; must run inside an application context.
    """
    with app.app_context():
        from models.database import db, Website, CheckHistory

        website = Website.query.get(website_id)
        if not website:
            return

        start = time.time()
        status      = "offline"
        response_time = None
        status_code   = None

        try:
            response = requests.get(
                website.url,
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": "Serenia-Uptime-Monitor/1.0"},
                allow_redirects=True,
            )
            elapsed       = (time.time() - start) * 1000  # ms
            response_time = round(elapsed, 2)
            status_code   = response.status_code
            status        = "online" if 200 <= status_code < 400 else "offline"

        except requests.exceptions.Timeout:
            logger.warning("Timeout checking %s", website.url)
            status_code = None

        except requests.exceptions.ConnectionError:
            logger.warning("Connection error checking %s", website.url)
            status_code = None

        except requests.exceptions.RequestException as exc:
            logger.error("Request error checking %s: %s", website.url, exc)
            status_code = None

        # Persist result
        history = CheckHistory(
            website_id=website_id,
            timestamp=datetime.utcnow(),
            status=status,
            response_time=response_time,
            status_code=status_code,
        )
        db.session.add(history)

        # Update website snapshot
        website.last_checked   = datetime.utcnow()
        website.current_status = status
        website.response_time  = response_time
        website.status_code    = status_code

        db.session.commit()
        logger.info("Checked %s → %s (%s ms)", website.url, status, response_time)


def check_all_websites(app):
    """Iterate every registered website and check it."""
    with app.app_context():
        from models.database import Website
        websites = Website.query.all()
        logger.info("Running scheduled check for %d website(s)", len(websites))
        for site in websites:
            try:
                check_website(app, site.id)
            except Exception as exc:  # noqa: BLE001
                logger.error("Unexpected error checking site %d: %s", site.id, exc)


def start_scheduler(app):
    """Start the background monitoring scheduler."""
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
    scheduler.start()
    logger.info("Monitoring scheduler started (interval=%ds)", CHECK_INTERVAL)


def stop_scheduler():
    """Gracefully stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Monitoring scheduler stopped")
