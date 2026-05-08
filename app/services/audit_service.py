from flask import request
from flask_login import current_user

from app.extensions import db
from app.models import AuditLog


def record_audit(action, module, record_id=None, old_data=None, new_data=None, user_id=None):
    actor_id = user_id
    if actor_id is None and current_user and current_user.is_authenticated:
        actor_id = current_user.id
    entry = AuditLog(
        user_id=actor_id,
        action=action,
        module=module,
        record_id=record_id,
        old_data=old_data,
        new_data=new_data,
        ip_address=request.remote_addr if request else None,
        user_agent=request.user_agent.string[:255] if request and request.user_agent else None,
    )
    db.session.add(entry)
    return entry
