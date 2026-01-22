# admin_utils.py
# Small helper decorator to protect admin-only endpoints.

from functools import wraps
from flask import jsonify
from flask_login import current_user, login_required

def admin_required(fn):
    """
    Ensures the user is logged in AND has is_admin=True.
    Returns 403 if not an admin.
    """
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not getattr(current_user, "is_admin", False):
            return jsonify({"error": "forbidden"}), 403
        return fn(*args, **kwargs)
    return wrapper
