# app.py
# Flask application entrypoint and factory.
# - Creates DB tables on startup
from flask import Flask, jsonify, render_template, abort
from pathlib import Path
from flask_login import LoginManager
from flask_login import login_required
from mock_exam import mock_exam_bp
from flask_login import current_user
from sqlalchemy import func

# DB setup
from db import engine, Base, SessionLocal



# Ensure models are imported so SQLAlchemy knows about them noqa f401 stops warning
from models import AnalysisLog, User ,ExamSession, ExamTurn, Base  # noqa: F401  (imported for side-effect)
from db import engine
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


    # calls the mock exam page requires login
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


    # Calls the developer dashboard requires user to be logged in as developer4
    @app.get("/developer")
    @login_required
    def developer_dashboard():
        if not current_user.is_admin:
            abort(403)

        db = SessionLocal()

        #  Basic Stats
        total_users = db.query(User).count()
        total_exams = db.query(ExamSession).count()
        completed_exams = db.query(ExamSession).filter_by(status="completed").count()
        in_progress_exams = db.query(ExamSession).filter_by(status="in_progress").count()

        #  User Preferences
        language_distribution = (
            db.query(User.preferred_language, func.count())
            .group_by(User.preferred_language)
            .all()
        )

        difficulty_distribution = (
            db.query(User.preferred_difficulty, func.count())
            .group_by(User.preferred_difficulty)
            .all()
        )



        #  Recent Exam Sessions
        recent_sessions = (
            db.query(ExamSession)
            .order_by(ExamSession.started_at.desc())
            .limit(20)
            .all()
        )


        #  Completion Rate
        total_sessions = db.query(ExamSession).count()
        completed_sessions = db.query(ExamSession).filter_by(status="completed").count()

        completion_rate = 0
        if total_sessions > 0:
            completion_rate = round((completed_sessions / total_sessions) * 100, 1)

        #  Exam Language Distribution
        exam_language_dist = (
            db.query(ExamSession.language, func.count())
            .group_by(ExamSession.language)
            .all()
        )

        #  Exam Difficulty Distribution
        exam_difficulty_dist = (
            db.query(ExamSession.difficulty, func.count())
            .group_by(ExamSession.difficulty)
            .all()
        )

        #  Average Questions Per Session
        avg_questions = db.query(func.avg(ExamSession.total_questions)).scalar()

        #  Average Overall Band
        avg_band = db.query(func.avg(ExamTurn.overall_band)).scalar()

        #  Most Active Users
        most_active_users = (
            db.query(ExamSession.user_id, func.count().label("session_count"))
            .group_by(ExamSession.user_id)
            .order_by(func.count().desc())
            .limit(5)
            .all()
        )

        db.close()

        return render_template(
            "developer.html",
            total_users=total_users,
            total_exams=total_exams,
            completed_exams=completed_exams,
            in_progress_exams=in_progress_exams,
            language_distribution=language_distribution,
            difficulty_distribution=difficulty_distribution,
            recent_sessions=recent_sessions,
            completion_rate=completion_rate,
            exam_language_dist=exam_language_dist,
            exam_difficulty_dist=exam_difficulty_dist,
            avg_questions=avg_questions,
            avg_band=avg_band,
            most_active_users=most_active_users
        )

    #  REGISTER BLUEPRINTS-
    app.register_blueprint(bp_ai)       # /api/... (AI feedback)
    app.register_blueprint(bp_crud)     # /api/... (CRUD logs)
    app.register_blueprint(bp_speech)   # /api/... (STT / TTS / streaming answer)
    app.register_blueprint(bp_auth)     # ( for user login)
    app.register_blueprint(bp_admin)  # /admin/... (admin-only)
    app.register_blueprint(bp_user)  # /api/user/... (user preferences)
    app.register_blueprint(mock_exam_bp)

    @app.get("/developer/session/<int:session_id>")
    @login_required
    def view_session(session_id):
        if not current_user.is_admin:
            abort(403)

        db = SessionLocal()

        session = db.get(ExamSession, session_id)
        if not session:
            db.close()
            abort(404)

        turns = (
            db.query(ExamTurn)
            .filter_by(session_id=session_id)
            .order_by(ExamTurn.question_number)
            .all()
        )

        db.close()

        return render_template(
            "developer_session.html",
            session=session,
            turns=turns
        )


    # Optional: simple 404 for convenience during dev
    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "not found"}), 404

    return app

    app = create_app()

    if __name__ == "__main__":
        app.run(debug=True)

""" ChatGPT Prompt 
Write two Flask route functions called audit_view and audit_clear.

Requirements:

Use Flask and Flask-Login.

Both routes must require authentication using @login_required.

The audit log is stored in a text file called supervisor_log.txt in the current working directory.

Use Path from pathlib to access the file.

audit_view:

Route should be GET /audit

If the file does not exist or is empty, return "No audit entries yet.\n" as plain text.

Otherwise read the file and return its contents as plain text using app.response_class.

The MIME type must be "text/plain".

audit_clear:

Route should be POST /audit/clear

It should erase the contents of supervisor_log.txt.

If the file does not exist, create it and leave it empty.

Return a simple confirmation message.

The code should be minimal and suitable for a Flask application file."""



""" ChatGPT Prompt 
Create a Flask route `/developer` called `developer_dashboard`.

The route should:

* require login using Flask-Login
* restrict access to admin users (`current_user.is_admin`)
* query a SQLAlchemy database for analytics about exam sessions

Calculate:

* total users
* total exams
* completed exams
* in-progress exams
* completion rate
* average questions per exam
* average band score
* exam language distribution
* exam difficulty distribution
* most active users
* recent exam sessions

Render the results in `developer.html`.
"""