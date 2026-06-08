"""
Serenia Uptime — Main Flask Application
Reliable Monitoring. Continuous Availability.
Features: IST timestamps, total views, SMS alerts, dev tracker
"""

import csv
import io
import logging
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import (
    Flask, Response, flash, jsonify,
    redirect, render_template, request, url_for,
)
from flask_wtf.csrf import CSRFProtect

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"]          = os.environ.get("SECRET_KEY", "serenia-dev-secret-change-in-prod")
    app.config["WTF_CSRF_ENABLED"]    = True

    # Database
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    if not database_url:
        if os.environ.get("RENDER"):
            db_path = "/tmp/serenia.db"
        else:
            os.makedirs("instance", exist_ok=True)
            db_path = os.path.join(os.path.abspath("instance"), "serenia.db")
        database_url = f"sqlite:///{db_path}"

    logger.info("Database: %s", database_url.split("@")[-1])
    app.config["SQLALCHEMY_DATABASE_URI"]        = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    from models.database import db
    db.init_app(app)
    CSRFProtect(app)

    with app.app_context():
        db.create_all()
        logger.info("Database tables ready")

    from monitoring.monitor import start_scheduler
    start_scheduler(app)

    register_routes(app)
    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalise_url(raw: str) -> str:
    raw = raw.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    if not urlparse(raw).netloc:
        raise ValueError("Invalid URL")
    return raw


def ist_now_str():
    return datetime.now(IST).strftime("%I:%M %p  %d %b %Y IST")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def register_routes(app: Flask):
    from models.database import db, Website, CheckHistory, AlertContact, Commit, to_ist
    from monitoring.monitor import check_website

    # ---- Landing ----
    @app.route("/")
    def landing():
        return render_template("landing.html")

    # ---- Dashboard ----
    @app.route("/dashboard")
    def dashboard():
        query  = request.args.get("q", "").strip()
        status = request.args.get("status", "").strip()

        q = Website.query
        if query:
            q = q.filter(
                Website.website_name.ilike(f"%{query}%") |
                Website.url.ilike(f"%{query}%")
            )
        if status in ("online", "offline", "unknown"):
            q = q.filter(Website.current_status == status)

        sites   = q.order_by(Website.created_at.desc()).all()
        total   = len(sites)
        online  = sum(1 for s in sites if s.current_status == "online")
        offline = sum(1 for s in sites if s.current_status == "offline")
        avg_rt  = (
            round(sum(s.response_time for s in sites if s.response_time) /
                  max(1, sum(1 for s in sites if s.response_time)), 2)
            if any(s.response_time for s in sites) else 0
        )
        last = Website.query.order_by(Website.last_checked.desc()).first()
        last_checked_str = to_ist(last.last_checked) if last and last.last_checked else "Never"

        return render_template(
            "dashboard.html",
            sites=sites, total=total, online=online, offline=offline,
            avg_rt=avg_rt, last_checked_str=last_checked_str,
            query=query, status_filter=status,
        )

    # ---- Add website ----
    @app.route("/add", methods=["GET", "POST"])
    def add_website():
        if request.method == "POST":
            name = request.form.get("website_name", "").strip()
            url  = request.form.get("url", "").strip()
            if not name:
                flash("Website name is required.", "error")
                return redirect(url_for("add_website"))
            if not url:
                flash("URL is required.", "error")
                return redirect(url_for("add_website"))
            try:
                url = normalise_url(url)
            except ValueError:
                flash("Please enter a valid URL.", "error")
                return redirect(url_for("add_website"))
            if Website.query.filter_by(url=url).first():
                flash("This URL is already being monitored.", "error")
                return redirect(url_for("add_website"))

            site = Website(website_name=name, url=url)
            db.session.add(site)
            db.session.commit()
            try:
                check_website(app, site.id)
            except Exception:
                pass
            flash(f'"{name}" added and is now being monitored.', "success")
            return redirect(url_for("dashboard"))
        return render_template("add_website.html")

    # ---- Delete website ----
    @app.route("/delete/<int:site_id>", methods=["POST"])
    def delete_website(site_id):
        site = Website.query.get_or_404(site_id)
        name = site.website_name
        db.session.delete(site)
        db.session.commit()
        flash(f'"{name}" removed from monitoring.', "success")
        return redirect(url_for("dashboard"))

    # ---- Analytics ----
    @app.route("/analytics")
    def analytics():
        sites = Website.query.order_by(Website.created_at.desc()).all()
        return render_template("analytics.html", sites=sites)

    # ---- Site detail (counts as a view) ----
    @app.route("/site/<int:site_id>")
    def site_detail(site_id):
        site = Website.query.get_or_404(site_id)
        site.total_views = (site.total_views or 0) + 1
        db.session.commit()
        history = (
            CheckHistory.query
            .filter_by(website_id=site_id)
            .order_by(CheckHistory.timestamp.desc())
            .limit(200).all()
        )
        return render_template("site_detail.html", site=site, history=history)

    # ---- Alerts page ----
    @app.route("/alerts", methods=["GET", "POST"])
    def alerts():
        if request.method == "POST":
            action = request.form.get("action")
            if action == "add":
                phone = request.form.get("phone", "").strip()
                label = request.form.get("label", "").strip()
                if not phone:
                    flash("Phone number is required.", "error")
                elif AlertContact.query.filter_by(phone=phone).first():
                    flash("This number is already registered.", "error")
                else:
                    db.session.add(AlertContact(phone=phone, label=label))
                    db.session.commit()
                    flash(f"Alert contact {phone} added.", "success")
            elif action == "delete":
                cid = request.form.get("contact_id", type=int)
                c   = AlertContact.query.get(cid)
                if c:
                    db.session.delete(c)
                    db.session.commit()
                    flash("Contact removed.", "success")
        contacts = AlertContact.query.order_by(AlertContact.created_at.desc()).all()
        twilio_ok = all([
            os.environ.get("TWILIO_ACCOUNT_SID"),
            os.environ.get("TWILIO_AUTH_TOKEN"),
            os.environ.get("TWILIO_FROM_NUMBER"),
        ])
        return render_template("alerts.html", contacts=contacts, twilio_ok=twilio_ok)

    # ---- Dev tracker ----
    @app.route("/devtracker")
    def devtracker():
        commits = Commit.query.order_by(Commit.committed_at.desc()).limit(50).all()
        repo    = os.environ.get("GITHUB_REPO", "")
        return render_template("devtracker.html", commits=commits, repo=repo)

    # ---- API: sites ----
    @app.route("/api/sites")
    def api_sites():
        return jsonify([s.to_dict() for s in Website.query.all()])

    @app.route("/api/site/<int:site_id>/history")
    def api_site_history(site_id):
        limit   = request.args.get("limit", 50, type=int)
        history = (CheckHistory.query.filter_by(website_id=site_id)
                   .order_by(CheckHistory.timestamp.desc()).limit(limit).all())
        return jsonify([h.to_dict() for h in history])

    @app.route("/api/site/<int:site_id>/check", methods=["POST"])
    def api_manual_check(site_id):
        site = Website.query.get_or_404(site_id)
        try:
            check_website(app, site.id)
            db.session.refresh(site)
            return jsonify({"success": True, "site": site.to_dict()})
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/stats")
    def api_stats():
        sites   = Website.query.all()
        total   = len(sites)
        online  = sum(1 for s in sites if s.current_status == "online")
        offline = sum(1 for s in sites if s.current_status == "offline")
        avg_rt  = (
            round(sum(s.response_time for s in sites if s.response_time) /
                  max(1, sum(1 for s in sites if s.response_time)), 2)
            if any(s.response_time for s in sites) else 0
        )
        return jsonify({"total": total, "online": online, "offline": offline,
                        "unknown": total - online - offline, "avg_response_time": avg_rt})

    # ---- Export CSV ----
    @app.route("/export/<int:site_id>/csv")
    def export_csv(site_id):
        site    = Website.query.get_or_404(site_id)
        history = (CheckHistory.query.filter_by(website_id=site_id)
                   .order_by(CheckHistory.timestamp.desc()).all())
        output  = io.StringIO()
        writer  = csv.writer(output)
        writer.writerow(["Timestamp (IST)", "Status", "Response Time (ms)", "Status Code"])
        for h in history:
            writer.writerow([to_ist(h.timestamp), h.status, h.response_time or "", h.status_code or ""])
        output.seek(0)
        filename = f"{site.website_name.replace(' ', '_')}_history.csv"
        return Response(output.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={filename}"})

    # ---- Error handlers ----
    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, message="Page not found"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("error.html", code=500, message="Internal server error"), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port,
            debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
