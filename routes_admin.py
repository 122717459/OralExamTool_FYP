# routes_admin.py
from flask import Blueprint, jsonify
from sqlalchemy import select

from db import SessionLocal
from models import User, AnalysisLog
from admin_utils import admin_required

bp_admin = Blueprint("admin", __name__, url_prefix="/admin")


@bp_admin.get("/users")
@admin_required
def admin_list_users():
    """
    Admin: list all users.
    """
    db = SessionLocal()
    try:
        users = db.execute(select(User).order_by(User.id.asc())).scalars().all()
        return jsonify([
            {
                "id": u.id,
                "email": u.email,
                "is_admin": bool(u.is_admin),
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in users
        ]), 200
    finally:
        db.close()


@bp_admin.delete("/users/<int:user_id>")
@admin_required
def admin_delete_user(user_id: int):
    """
    Admin: delete a user.
    (Does NOT automatically delete their logs. We can add cascade later if you want.)
    """
    db = SessionLocal()
    try:
        u = db.get(User, user_id)
        if not u:
            return jsonify({"error": "not found"}), 404

        # Safety: prevent deleting an admin account (optional but recommended)
        if u.is_admin:
            return jsonify({"error": "cannot delete an admin user"}), 400

        db.delete(u)
        db.commit()
        return jsonify({"deleted_user_id": user_id}), 200
    finally:
        db.close()


@bp_admin.get("/logs")
@admin_required
def admin_list_all_logs():
    """
    Admin: view all logs (unfiltered).
    """
    db = SessionLocal()
    try:
        logs = db.execute(select(AnalysisLog).order_by(AnalysisLog.id.desc())).scalars().all()
        return jsonify([
            {
                "id": l.id,
                "user_id": l.user_id,
                "input_text": l.input_text,
                "feedback_text": l.feedback_text,
                "model_name": l.model_name,
                "created_at": l.created_at.isoformat() if l.created_at else None
            }
            for l in logs
        ]), 200
    finally:
        db.close()
