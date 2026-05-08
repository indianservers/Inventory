from datetime import datetime
from app.extensions import db


class Attachment(db.Model):
    __tablename__ = "attachments"
    id = db.Column(db.Integer, primary_key=True)
    module = db.Column(db.String(50), nullable=False)
    record_id = db.Column(db.Integer, nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255))
    mime_type = db.Column(db.String(100))
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
