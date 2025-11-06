
# Simple CRUD API for the Analysislog table.
# We import Flask for building the API
from flask import Blueprint, request, jsonify

# SQLAlchemy tools to talk to the database
from sqlalchemy import select, func
from sqlalchemy.orm import Session

# These are from this project, they set up the DB connection and model
from db import get_db
from models import AnalysisLog
from audit import write_event

# We make a "Blueprint"  a container for related routes
# This makes it easy to group CRUD endpoints under /api
bp_crud = Blueprint("crud", __name__, url_prefix="/api")


# Get a database session. Our get_db() yields one; we just grab it.
def db_session():
    return next(get_db())



# Turn a DB row into a plain dict that jsonify() can handle.
def to_dict(row: AnalysisLog):
    return {
        "id": row.id,
        "input_text": row.input_text,
        "feedback_text": row.feedback_text,
        "model_name": row.model_name,
        #  convert it to a readable string (ISO format)
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


#  READ (LIST)
@bp_crud.get("/logs")
def list_logs():
    """
    GET /api/logs
    Returns a page of logs. You can pass ?page=2&per_page=20.
    """

    # Read paging values safely. If someone sends junk, we fall back.
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(max(int(request.args.get("per_page", 10)), 1), 100)

    # Open a database session using a context manager
    with db_session() as db:  # type: Session

        # Build a base SELECT query
        stmt = select(AnalysisLog)

        # Count how many total rows exist for pagination
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))

        # fetch one "page" of results
        # Order newest first (highest id)
        rows = db.execute(
            stmt.order_by(AnalysisLog.id.desc()).limit(per_page).offset((page - 1) * per_page)
        ).scalars().all()

        # Turn the rows into dicts and return them as JSON
        return jsonify({
            "page": page,
            "per_page": per_page,
            "total": total,
            "items": [to_dict(r) for r in rows]
        }), 200


#  READ (ONE)
@bp_crud.get("/logs/<int:log_id>")
def get_log(log_id: int):
    # Fetch one log by ID, like GET /api/logs/5
    with db_session() as db:  # type: Session
        row = db.get(AnalysisLog, log_id)
        if not row:
            # If nothing found, return a 404
            return jsonify({"error": "not found"}), 404

        # Otherwise return it as JSON
        return jsonify(to_dict(row)), 200


#  CREATE
@bp_crud.post("/logs")
def create_log():
    """
    POST /api/logs creates a new log record.
    The client must send JSON like:
    {
      "input_text": "some input",
      "feedback_text": "some feedback",
      "model_name": "gpt-4o-mini",
      "scores": { ... }
    }
    """

    # Parse the incoming JSON body
    data = request.get_json(force=True) or {}

    # Extract and clean the data
    input_text = (data.get("input_text") or "").strip()
    feedback_text = (data.get("feedback_text") or "").strip()
    model_name = (data.get("model_name") or "manual").strip()
    scores = data.get("scores") or {}

    # Make sure the two required fields exist
    if not input_text or not feedback_text:
        return jsonify({"error": "input_text and feedback_text are required"}), 400

    with db_session() as db:  # type: Session
        # Create a new AnalysisLog row
        row = AnalysisLog(
            input_text=input_text,
            feedback_text=feedback_text,
            model_name=model_name,
        )
        db.add(row)
        db.commit()  # Save so, it gets an ID

        # # Update score columns only if provided and valid
        changed = False
        mapping = {
            "score_overall": scores.get("overall"),
            "score_grammar": scores.get("grammar"),
            "score_fluency": scores.get("fluency"),
            "score_pronunciation": scores.get("pronunciation"),
        }

        # Only update the ones that exist and have values
        for k, v in mapping.items():
            if hasattr(row, k) and v is not None:
                setattr(row, k, int(v))
                changed = True

        if changed:
            db.add(row)
            db.commit()

        # Reload the record with any DB-generated values (like timestamps)
        db.refresh(row)

        # Log this event somewhere (function is defined elsewhere)
        write_event("CREATE", {
            "id": row.id,
            "model": row.model_name,
            "input_chars": len(row.input_text or "")
        })

        # Return the created row and a 201 status (Created)
        return jsonify(to_dict(row)), 201


#  UPDATE
@bp_crud.put("/logs/<int:log_id>")
def update_log(log_id: int):
    """
    PUT /api/logs/123 — change any fields you send in.
    """

    data = request.get_json(force=True) or {}
    with db_session() as db:  # type: Session
        row = db.get(AnalysisLog, log_id)
        if not row:
            return jsonify({"error": "not found"}), 404

        # Update text fields if provided
        if "input_text" in data and data["input_text"] is not None:
            row.input_text = data["input_text"].strip()
        if "feedback_text" in data and data["feedback_text"] is not None:
            row.feedback_text = data["feedback_text"].strip()
        if "model_name" in data and data["model_name"] is not None:
            row.model_name = data["model_name"].strip()

        # Update scores (if provided)
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

        # Save updates
        db.add(row)
        db.commit()
        db.refresh(row)

        # Log that we updated
        write_event("UPDATE", {
            "id": row.id,
            "model": row.model_name
        })

        return jsonify(to_dict(row)), 200


#  DELETE
@bp_crud.delete("/logs/<int:log_id>")
def delete_log(log_id: int):
    # DELETE /api/logs/5 removes the record completely
    with db_session() as db:  # type: Session
        row = db.get(AnalysisLog, log_id)
        if not row:
            return jsonify({"error": "not found"}), 404

        db.delete(row)
        db.commit()

        # Log the deletion
        write_event("DELETE", {"id": log_id})

        # Respond with confirmation
        return jsonify({"deleted": log_id}), 200
