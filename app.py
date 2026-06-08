"""
Serenia Uptime — Main Flask Application
Reliable Monitoring. Continuous Availability.
"""

import csv
import io
import logging
import os
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_wtf.csrf import CSRFProtect

load_dotenv()

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> Flask:
    app = Flask(__name__)

    # ---- Configuration ----
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "serenia-dev-secret-change-in-prod")
    app.config["WTF_CSRF_ENABLED"] = True

    database_url = os.environ.get("DATABASE_URL", "sqlite:///instance/serenia.db")
    # Render provides postgres:// URIs; SQLAlchemy needs postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ---- Extensions ----
    from models.database import db
    db.init_app(app)

    csrf = CSRFProtect(app)

    # ---- Database init ----
    with app.app_context():
        os.makedirs("instance", exist_ok=True)
        db.create_all()

    # ---- Monitoring scheduler ----
    from monitoring.monitor import start_scheduler
    start_scheduler(app)

    # ---- Register routes ----
    register_routes(app, csrf)

    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

URL_REGEX = re.compile(
    r"^(https?://)?"                      # optional scheme
    r"(([a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,})" # domain
    r"(:[0-9]{1,5})?"                     # optional port
    r"(/[^\s]*)?$",                       # optional path
    re.IGNORECASE,
)


def normalise_url(raw: str) -> str:
    """Ensure URL has a scheme; raise ValueError if invalid."""
    raw = raw.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if not parsed.netloc:
        raise ValueError("Invalid URL")
    return raw


def register_routes(app: Flask, csrf: CSRFProtect):
    from models.database import db, Website, CheckHistory
    from monitoring.monitor import check_website

    # ------------------------------------------------------------------ #
    #  Landing page                                                        #
    # ------------------------------------------------------------------ #

    @app.route("/")
    def landing():
        return render_template("landing.html")

    # ------------------------------------------------------------------ #
    #  Dashboard                                                           #
    # ------------------------------------------------------------------ #

    @app.route("/dashboard")
    def dashboard():
        query  = request.args.get("q", "").strip()
        status = request.args.get("status", "").strip()

        sites = Website.query
        if query:
            sites = sites.filter(
                (Website.website_name.ilike(f"%{query}%")) |
                (Website.url.ilike(f"%{query}%"))
            )
        if status in ("online", "offline", "unknown"):
            sites = sites.filter(Website.current_status == status)

        sites = sites.order_by(Website.created_at.desc()).all()

        total   = len(sites)
        online  = sum(1 for s in sites if s.current_status == "online")
        offline = sum(1 for s in sites if s.current_status == "offline")
        avg_rt  = (
            round(
                sum(s.response_time for s in sites if s.response_time) /
                max(1, sum(1 for s in sites if s.response_time)),
                2,
            )
            if any(s.response_time for s in sites) else 0
        )

        last_activity = (
            Website.query.order_by(Website.last_checked.desc()).first()
        )
        last_checked_str = (
            last_activity.last_checked.strftime("%H:%M:%S %d %b %Y")
            if last_activity and last_activity.last_checked else "Never"
        )

        return render_template(
            "dashboard.html",
            sites=sites,
            total=total,
            online=online,
            offline=offline,
            avg_rt=avg_rt,
            last_checked_str=last_checked_str,
            query=query,
            status_filter=status,
        )

    # ------------------------------------------------------------------ #
    #  Add website                                                         #
    # ------------------------------------------------------------------ #

    @app.route("/add", methods=["GET", "POST"])
    def add_website():
        if request.method == "POST":
            name = request.form.get("website_name", "").strip()
            url  = request.form.get("url", "").strip()

            # Validation
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

            # Immediate first check
            try:
                check_website(app, site.id)
            except Exception:  # noqa: BLE001
                pass

            flash(f'"{name}" has been added and is now being monitored.', "success")
            return redirect(url_for("dashboard"))

        return render_template("add_website.html")

    # ------------------------------------------------------------------ #
    #  Delete website                                                      #
    # ------------------------------------------------------------------ #

    @app.route("/delete/<int:site_id>", methods=["POST"])
    def delete_website(site_id):
        site = Website.query.get_or_404(site_id)
        name = site.website_name
        db.session.delete(site)
        db.session.commit()
        flash(f'"{name}" has been removed from monitoring.', "success")
        return redirect(url_for("dashboard"))

    # ------------------------------------------------------------------ #
    #  Analytics page                                                      #
    # ------------------------------------------------------------------ #

    @app.route("/analytics")
    def analytics():
        sites = Website.query.order_by(Website.created_at.desc()).all()
        return render_template("analytics.html", sites=sites)

    # ------------------------------------------------------------------ #
    #  Site detail / history                                               #
    # ------------------------------------------------------------------ #

    @app.route("/site/<int:site_id>")
    def site_detail(site_id):
        site    = Website.query.get_or_404(site_id)
        history = (
            CheckHistory.query
            .filter_by(website_id=site_id)
            .order_by(CheckHistory.timestamp.desc())
            .limit(200)
            .all()
        )
        return render_template("site_detail.html", site=site, history=history)

    # ------------------------------------------------------------------ #
    #  API endpoints (consumed by JS)                                     #
    # ------------------------------------------------------------------ #

    @app.route("/api/sites")
    def api_sites():
        sites = Website.query.all()
        return jsonify([s.to_dict() for s in sites])

    @app.route("/api/site/<int:site_id>/history")
    def api_site_history(site_id):
        limit   = request.args.get("limit", 50, type=int)
        history = (
            CheckHistory.query
            .filter_by(website_id=site_id)
            .order_by(CheckHistory.timestamp.desc())
            .limit(limit)
            .all()
        )
        return jsonify([h.to_dict() for h in history])

    @app.route("/api/site/<int:site_id>/check", methods=["POST"])
    def api_manual_check(site_id):
        """Trigger an immediate check for a single website."""
        site = Website.query.get_or_404(site_id)
        try:
            check_website(app, site.id)
            db.session.refresh(site)
            return jsonify({"success": True, "site": site.to_dict()})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/stats")
    def api_stats():
        sites   = Website.query.all()
        total   = len(sites)
        online  = sum(1 for s in sites if s.current_status == "online")
        offline = sum(1 for s in sites if s.current_status == "offline")
        avg_rt  = (
            round(
                sum(s.response_time for s in sites if s.response_time) /
                max(1, sum(1 for s in sites if s.response_time)),
                2,
            )
            if any(s.response_time for s in sites) else 0
        )
        return jsonify(
            {
                "total": total,
                "online": online,
                "offline": offline,
                "unknown": total - online - offline,
                "avg_response_time": avg_rt,
            }
        )

    # ------------------------------------------------------------------ #
    #  Export CSV                                                          #
    # ------------------------------------------------------------------ #

    @app.route("/export/<int:site_id>/csv")
    def export_csv(site_id):
        site    = Website.query.get_or_404(site_id)
        history = (
            CheckHistory.query
            .filter_by(website_id=site_id)
            .order_by(CheckHistory.timestamp.desc())
            .all()
        )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Timestamp", "Status", "Response Time (ms)", "Status Code"])
        for h in history:
            writer.writerow([
                h.timestamp.isoformat() if h.timestamp else "",
                h.status,
                h.response_time or "",
                h.status_code or "",
            ])

        output.seek(0)
        filename = f"{site.website_name.replace(' ', '_')}_history.csv"
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    # ------------------------------------------------------------------ #
    #  Error handlers                                                      #
    # ------------------------------------------------------------------ #

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
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
