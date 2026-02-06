# app.py
# Flask application entrypoint and factory.
# - Creates DB tables on startup
from flask import Flask, jsonify, render_template
from pathlib import Path
from flask_login import LoginManager
from flask_login import login_required

# DB setup
from db import engine, Base, SessionLocal


# Ensure models are imported so SQLAlchemy knows about them noqa f401 stops warning
from models import AnalysisLog, User ,ExamSession, ExamTurn  # noqa: F401  (imported for side-effect)

# Blueprints
from routes_ai import bp_ai
from routes_crud import bp_crud
from routes_speech import bp_speech
from routes_auth import bp_auth
from routes_admin import bp_admin
from routes_user import bp_user


# Calls Flask app to start
def create_app() -> Flask:
    app = Flask(__name__)

    app.config["SECRET_KEY"] = "dev-change-this"

    # Create any missing tables
    Base.metadata.create_all(bind=engine)
    # Flask-Login setup
    login_manager = LoginManager()
    login_manager.login_view = "auth.login_get"  # where to redirect if not logged in
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        # Flask-Login stores user_id in the session as a string
        db = SessionLocal()
        try:
            return db.get(User, int(user_id))
        finally:
            db.close()


    # Shows that the database is working
    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    # Is another check on the database
    @app.get("/db-check")
    def db_check():
        from sqlalchemy import text
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM analysis_logs"))
            count = result.scalar_one()
        return jsonify({"analysis_logs_count": count}), 200

# Checking the database created the new exam tabel
    @app.get("/db-check-exams")
    def db_check_exams():
        from sqlalchemy import text
        with engine.connect() as conn:
            sessions = conn.execute(text("SELECT COUNT(*) FROM exam_sessions")).scalar_one()
            turns = conn.execute(text("SELECT COUNT(*) FROM exam_turns")).scalar_one()
        return jsonify({"exam_sessions_count": sessions, "exam_turns_count": turns}), 200


    # Calls the Index.html page also requires the user to be logged in
    @app.get("/")
    @login_required
    def home():
        return render_template("index.html")

    #  AUDIT VIEW
    # This code is from ChatGPT
    @app.get("/audit")
    @login_required
    def audit_view():
        p = Path("supervisor_log.txt")
        if not p.exists() or p.stat().st_size == 0:
            return app.response_class("No audit entries yet.\n", mimetype="text/plain")
        return app.response_class(p.read_text(encoding="utf-8"), mimetype="text/plain")
    # Uses Path("supervisor_log.txt") in the current working directory
    #If the file doesn't exist or is empty returns message.
    # Otherwise reads the file and returns it as text.
    #  AUDIT CLEAR

    @app.get("/mock")
    @login_required
    def mock_exam_page():
        return render_template("mock_exam.html")

    # This code is from ChatGPT
    @app.post("/audit/clear")
    @login_required
    def audit_clear():
        Path("supervisor_log.txt").write_text("", encoding="utf-8")
        return jsonify({"status": "cleared"}), 200

    #  REGISTER BLUEPRINTS-

    #This code is from ChatGPT
    # Note: register each blueprint exactly once
    app.register_blueprint(bp_ai)       # /api/... (AI feedback)
    app.register_blueprint(bp_crud)     # /api/... (CRUD logs)
    app.register_blueprint(bp_speech)   # /api/... (STT / TTS / streaming answer)
    app.register_blueprint(bp_auth)     # ( for user login)
    app.register_blueprint(bp_admin)  # /admin/... (admin-only)
    app.register_blueprint(bp_user)  # /api/user/... (user preferences)

    # Optional: simple 404 for convenience during dev
    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "not found"}), 404

    return app


if __name__ == "__main__":
    app = create_app()
    # Use port 8000 to match your previous setup
    app.run(debug=True, port=8000)


