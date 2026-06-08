"""
Serenia Uptime - Database Models
Defines Website and CheckHistory models using SQLAlchemy.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Website(db.Model):
    """Represents a monitored website."""
    __tablename__ = "websites"

    id = db.Column(db.Integer, primary_key=True)
    website_name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_checked = db.Column(db.DateTime, nullable=True)
    current_status = db.Column(db.String(20), default="unknown")  # online / offline / unknown
    response_time = db.Column(db.Float, nullable=True)            # milliseconds
    status_code = db.Column(db.Integer, nullable=True)

    # Relationship to check history
    checks = db.relationship("CheckHistory", backref="website", lazy=True, cascade="all, delete-orphan")

    def uptime_percentage(self):
        """Calculate uptime % from the last 100 checks."""
        total = CheckHistory.query.filter_by(website_id=self.id).count()
        if total == 0:
            return 100.0
        successful = CheckHistory.query.filter_by(website_id=self.id, status="online").count()
        return round((successful / total) * 100, 2)

    def consecutive_failures(self):
        """Return number of consecutive failures from the most recent checks."""
        recent = (
            CheckHistory.query
            .filter_by(website_id=self.id)
            .order_by(CheckHistory.timestamp.desc())
            .limit(50)
            .all()
        )
        count = 0
        for check in recent:
            if check.status == "offline":
                count += 1
            else:
                break
        return count

    def to_dict(self):
        return {
            "id": self.id,
            "website_name": self.website_name,
            "url": self.url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "current_status": self.current_status,
            "response_time": self.response_time,
            "status_code": self.status_code,
            "uptime_percentage": self.uptime_percentage(),
            "consecutive_failures": self.consecutive_failures(),
        }


class CheckHistory(db.Model):
    """Stores the result of each monitoring check."""
    __tablename__ = "check_history"

    id = db.Column(db.Integer, primary_key=True)
    website_id = db.Column(db.Integer, db.ForeignKey("websites.id"), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False)    # online / offline
    response_time = db.Column(db.Float, nullable=True)   # milliseconds
    status_code = db.Column(db.Integer, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "website_id": self.website_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "status": self.status,
            "response_time": self.response_time,
            "status_code": self.status_code,
        }
