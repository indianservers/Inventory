from datetime import datetime
from app.extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    module = db.Column(db.String(50), nullable=False)
    record_id = db.Column(db.Integer)
    old_data = db.Column(db.JSON)
    new_data = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User", backref="audit_logs")

