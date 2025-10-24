from flask import Blueprint, request, jsonify
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from db import get_db
from models import AnalysisLog

bp_crud = Blueprint("crud", __name__, url_prefix="/api")

def db_session():
    return next(get_db())

def to_dict(row: AnalysisLog):
    return {
        "id": row.id,
        "input_text": row.input_text,
        "feedback_text": row.feedback_text,
        "model_name": row.model_name,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }

# -------- READ (LIST) --------
@bp_crud.get("/logs")
def list_logs():
    """
    Query params:
      - page (default 1), per_page (default 10)
    """
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(max(int(request.args.get("per_page", 10)), 1), 100)

    with db_session() as db:  # type: Session
        stmt = select(AnalysisLog)
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = db.execute(
            stmt.order_by(AnalysisLog.id.desc()).limit(per_page).offset((page - 1) * per_page)
        ).scalars().all()

        return jsonify({
            "page": page,
            "per_page": per_page,
            "total": total,
            "items": [to_dict(r) for r in rows]
        }), 200

# -------- READ (ONE) --------
@bp_crud.get("/logs/<int:log_id>")
def get_log(log_id: int):
    with db_session() as db:  # type: Session
        row = db.get(AnalysisLog, log_id)
        if not row:
            return jsonify({"error": "not found"}), 404
        return jsonify(to_dict(row)), 200

# -------- CREATE --------
@bp_crud.post("/logs")
def create_log():
    """
    Body JSON (minimum):
    {
      "input_text": "text",
      "feedback_text": "text",
      "model_name": "gpt-4o-mini",
      "scores": { "overall": 75, "grammar": 80, "fluency": 70, "pronunciation": 68 }  # optional
    }
    """
    data = request.get_json(force=True) or {}
    input_text = (data.get("input_text") or "").strip()
    feedback_text = (data.get("feedback_text") or "").strip()
    model_name = (data.get("model_name") or "manual").strip()
    scores = data.get("scores") or {}

    if not input_text or not feedback_text:
        return jsonify({"error": "input_text and feedback_text are required"}), 400

    with db_session() as db:  # type: Session
        row = AnalysisLog(
            input_text=input_text,
            feedback_text=feedback_text,
            model_name=model_name,
        )
        db.add(row)
        db.commit()

        # Optional score fields if present in your DB
        changed = False
        mapping = {
            "score_overall": scores.get("overall"),
            "score_grammar": scores.get("grammar"),
            "score_fluency": scores.get("fluency"),
            "score_pronunciation": scores.get("pronunciation"),
        }
        for k, v in mapping.items():
            if hasattr(row, k) and v is not None:
                setattr(row, k, int(v))
                changed = True
        if changed:
            db.add(row)
            db.commit()

        db.refresh(row)
        write_event("CREATE", {
            "id": row.id,
            "model": row.model_name,
            "input_chars": len(row.input_text or "")
        })

        return jsonify(to_dict(row)), 201

# -------- UPDATE --------
@bp_crud.put("/logs/<int:log_id>")
def update_log(log_id: int):
    """
    Body JSON (any fields you want to change):
    {
      "input_text": "...",
      "feedback_text": "...",
      "model_name": "...",
      "scores": { "overall": 85, "grammar": 82, "fluency": 80, "pronunciation": 78 }
    }
    """
    data = request.get_json(force=True) or {}
    with db_session() as db:  # type: Session
        row = db.get(AnalysisLog, log_id)
        if not row:
            return jsonify({"error": "not found"}), 404

        if "input_text" in data and data["input_text"] is not None:
            row.input_text = data["input_text"].strip()
        if "feedback_text" in data and data["feedback_text"] is not None:
            row.feedback_text = data["feedback_text"].strip()
        if "model_name" in data and data["model_name"] is not None:
            row.model_name = data["model_name"].strip()

        scores = data.get("scores") or {}
        mapping = {
            "score_overall": scores.get("overall"),
            "score_grammar": scores.get("grammar"),
            "score_fluency": scores.get("fluency"),
            "score_pronunciation": scores.get("pronunciation"),
        }
        for k, v in mapping.items():
            if hasattr(row, k) and v is not None:
                setattr(row, k, int(v))

        db.add(row)
        db.commit()
        db.refresh(row)
        write_event("UPDATE", {
            "id": row.id,
            "model": row.model_name
        })

        return jsonify(to_dict(row)), 200

# -------- DELETE --------
@bp_crud.delete("/logs/<int:log_id>")
def delete_log(log_id: int):
    with db_session() as db:  # type: Session
        row = db.get(AnalysisLog, log_id)
        if not row:
            return jsonify({"error": "not found"}), 404
        db.delete(row)
        db.commit()
        write_event("DELETE", {"id": log_id})

        return jsonify({"deleted": log_id}), 200
