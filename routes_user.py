# routes_user.py
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from db import SessionLocal
from models import User

bp_user = Blueprint("user", __name__, url_prefix="/api/user")

ALLOWED_LANGUAGES = {"english", "french", "german"}
ALLOWED_DIFFICULTIES = {"beginner", "moderate", "expert"}

# Returns the preferences that the user has.
@bp_user.get("/preferences")
@login_required
def get_preferences():
    """
    Returns the logged-in user's saved preferences.
    """
    return jsonify({
        "preferred_language": getattr(current_user, "preferred_language", "english"),
        "preferred_difficulty": getattr(current_user, "preferred_difficulty", "moderate"),
    }), 200


# Updates the preferences if the user changes them.
@bp_user.post("/preferences")
@login_required
def update_preferences():
    """
    Updates the logged-in user's preferences.

    Expected JSON:
    {
      "preferred_language": "english" | "french" | "german",
      "preferred_difficulty": "beginner" | "moderate" | "expert"
    }
    """
    data = request.get_json(force=True) or {}

    lang = (data.get("preferred_language") or "").strip().lower()
    diff = (data.get("preferred_difficulty") or "").strip().lower()

    if lang and lang not in ALLOWED_LANGUAGES:
        return jsonify({"error": "invalid preferred_language"}), 400
    if diff and diff not in ALLOWED_DIFFICULTIES:
        return jsonify({"error": "invalid preferred_difficulty"}), 400

    db = SessionLocal()
    try:
        user = db.get(User, int(current_user.id))
        if not user:
            return jsonify({"error": "user not found"}), 404

        # Only update fields that were provided
        if lang:
            user.preferred_language = lang
        if diff:
            user.preferred_difficulty = diff

        db.add(user)
        db.commit()
        db.refresh(user)

        return jsonify({
            "preferred_language": user.preferred_language,
            "preferred_difficulty": user.preferred_difficulty,
        }), 200
    finally:
        db.close()
