# app.py
# Flask application entrypoint and factory.
# - Registers blueprints (AI, CRUD, Speech)
# - Adds health/db-check/audit routes
# - Creates DB tables on startup
from flask import Flask, jsonify, render_template
from pathlib import Path

# DB setup
from db import engine, Base

# Ensure models are imported so SQLAlchemy knows about them
from models import AnalysisLog  # noqa: F401  (imported for side-effect)

# Blueprints
from routes_ai import bp_ai
from routes_crud import bp_crud
from routes_speech import bp_speech


def create_app() -> Flask:
    app = Flask(__name__)

    # Create any missing tables (handy for local dev / PoC)
    Base.metadata.create_all(bind=engine)

    # ---------------- HEALTH ----------------
    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    # ---------------- DB CHECK ----------------
    @app.get("/db-check")
    def db_check():
        from sqlalchemy import text
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM analysis_logs"))
            count = result.scalar_one()
        return jsonify({"analysis_logs_count": count}), 200

    # ---------------- HOME ----------------
    @app.get("/")
    def home():
        return render_template("index.html")

    # ---------------- AUDIT VIEW ----------------
    @app.get("/audit")
    def audit_view():
        p = Path("supervisor_log.txt")
        if not p.exists() or p.stat().st_size == 0:
            return app.response_class("No audit entries yet.\n", mimetype="text/plain")
        return app.response_class(p.read_text(encoding="utf-8"), mimetype="text/plain")

    # ---------------- AUDIT CLEAR ----------------
    @app.post("/audit/clear")
    def audit_clear():
        Path("supervisor_log.txt").write_text("", encoding="utf-8")
        return jsonify({"status": "cleared"}), 200

    # ---------------- REGISTER BLUEPRINTS ----------------
    # Note: register each blueprint exactly once
    app.register_blueprint(bp_ai)       # /api/... (AI feedback)
    app.register_blueprint(bp_crud)     # /api/... (CRUD logs)
    app.register_blueprint(bp_speech)   # /api/... (STT / TTS / streaming answer)

    # Optional: simple 404 for convenience during dev
    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "not found"}), 404

    return app


if __name__ == "__main__":
    app = create_app()
    # Use port 8000 to match your previous setup
    app.run(debug=True, port=8000)


