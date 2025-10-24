from flask import Flask, jsonify, render_template
from pathlib import Path
from db import engine, Base
from models import AnalysisLog  # ensures model is registered
from routes_ai import bp_ai
from routes_crud import bp_crud


def create_app():
    app = Flask(__name__)

    # Create tables on startup (fine for PoC)
    Base.metadata.create_all(bind=engine)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @app.get("/db-check")
    def db_check():
        from sqlalchemy import text
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM analysis_logs"))
            count = result.scalar_one()
        return jsonify({"analysis_logs_count": count}), 200

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/audit")
    def audit_view():
        p = Path("supervisor_log.txt")
        if not p.exists() or p.stat().st_size == 0:
            return app.response_class("No audit entries yet.\n", mimetype="text/plain")
        return app.response_class(p.read_text(encoding="utf-8"), mimetype="text/plain")

    @app.post("/audit/clear")
    def audit_clear():
        Path("supervisor_log.txt").write_text("", encoding="utf-8")
        return jsonify({"status": "cleared"}), 200

    # Register blueprints
    app.register_blueprint(bp_ai)
    app.register_blueprint(bp_crud)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=8000)
