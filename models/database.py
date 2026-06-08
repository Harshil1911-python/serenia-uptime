"""
Serenia Uptime - Database Models
All timestamps stored in UTC, displayed in IST (UTC+5:30).
"""

from datetime import datetime, timezone, timedelta
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    """Return current IST datetime (stored as UTC-aware, displayed as IST)."""
    return datetime.now(timezone.utc)


def to_ist(dt):
    """Convert a UTC datetime to IST string for display."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ist_dt = dt.astimezone(IST)
    return ist_dt.strftime("%I:%M %p  %d %b %Y IST")


def to_ist_iso(dt):
    """Convert a UTC datetime to IST ISO string."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).isoformat()


class AlertContact(db.Model):
    """Phone numbers that receive SMS alerts when a site goes offline."""
    __tablename__ = "alert_contacts"

    id         = db.Column(db.Integer, primary_key=True)
    phone      = db.Column(db.String(20), nullable=False)
    label      = db.Column(db.String(100), default="")
    created_at = db.Column(db.DateTime(timezone=True), default=now_ist)

    def to_dict(self):
        return {
            "id":    self.id,
            "phone": self.phone,
            "label": self.label,
        }


class Website(db.Model):
    """Represents a monitored website."""
    __tablename__ = "websites"

    id             = db.Column(db.Integer, primary_key=True)
    website_name   = db.Column(db.String(200), nullable=False)
    url            = db.Column(db.String(500), nullable=False, unique=True)
    created_at     = db.Column(db.DateTime(timezone=True), default=now_ist)
    last_checked   = db.Column(db.DateTime(timezone=True), nullable=True)
    current_status = db.Column(db.String(20), default="unknown")
    response_time  = db.Column(db.Float, nullable=True)
    status_code    = db.Column(db.Integer, nullable=True)
    total_views    = db.Column(db.Integer, default=0)   # page-view counter

    checks = db.relationship(
        "CheckHistory", backref="website", lazy=True, cascade="all, delete-orphan"
    )

    def uptime_percentage(self):
        total = CheckHistory.query.filter_by(website_id=self.id).count()
        if total == 0:
            return 100.0
        ok = CheckHistory.query.filter_by(website_id=self.id, status="online").count()
        return round((ok / total) * 100, 2)

    def consecutive_failures(self):
        recent = (
            CheckHistory.query
            .filter_by(website_id=self.id)
            .order_by(CheckHistory.timestamp.desc())
            .limit(50).all()
        )
        count = 0
        for c in recent:
            if c.status == "offline":
                count += 1
            else:
                break
        return count

    def to_dict(self):
        return {
            "id":                  self.id,
            "website_name":        self.website_name,
            "url":                 self.url,
            "created_at":          to_ist_iso(self.created_at),
            "created_at_display":  to_ist(self.created_at),
            "last_checked":        to_ist_iso(self.last_checked),
            "last_checked_display": to_ist(self.last_checked),
            "current_status":      self.current_status,
            "response_time":       self.response_time,
            "status_code":         self.status_code,
            "uptime_percentage":   self.uptime_percentage(),
            "consecutive_failures": self.consecutive_failures(),
            "total_views":         self.total_views or 0,
        }


class CheckHistory(db.Model):
    """Stores the result of each monitoring check."""
    __tablename__ = "check_history"

    id            = db.Column(db.Integer, primary_key=True)
    website_id    = db.Column(db.Integer, db.ForeignKey("websites.id"), nullable=False)
    timestamp     = db.Column(db.DateTime(timezone=True), default=now_ist)
    status        = db.Column(db.String(20), nullable=False)
    response_time = db.Column(db.Float, nullable=True)
    status_code   = db.Column(db.Integer, nullable=True)

    def to_dict(self):
        return {
            "id":            self.id,
            "website_id":    self.website_id,
            "timestamp":     to_ist_iso(self.timestamp),
            "timestamp_display": to_ist(self.timestamp),
            "status":        self.status,
            "response_time": self.response_time,
            "status_code":   self.status_code,
        }


class Commit(db.Model):
    """Development tracker — stores commit records."""
    __tablename__ = "commits"

    id          = db.Column(db.Integer, primary_key=True)
    sha         = db.Column(db.String(40), nullable=False, unique=True)
    message     = db.Column(db.String(500), nullable=False)
    author      = db.Column(db.String(200), default="")
    committed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    fetched_at  = db.Column(db.DateTime(timezone=True), default=now_ist)

    def to_dict(self):
        return {
            "sha":           self.sha[:7],
            "message":       self.message,
            "author":        self.author,
            "committed_at":  to_ist(self.committed_at),
            "fetched_at":    to_ist(self.fetched_at),
        }
