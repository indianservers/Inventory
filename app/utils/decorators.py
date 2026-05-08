from functools import wraps
from flask import abort
from flask_login import current_user, login_required


def permission_required(module, action="view"):
    def outer(fn):
        @wraps(fn)
        @login_required
        def inner(*args, **kwargs):
            if not current_user.has_permission(module, action):
                abort(403)
            return fn(*args, **kwargs)

        return inner

    return outer

