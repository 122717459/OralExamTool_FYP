# migrate_add_user_id.py
from sqlalchemy import text, inspect
from db import engine

def main():
    inspector = inspect(engine)
    cols = [c["name"] for c in inspector.get_columns("analysis_logs")]

    if "user_id" in cols:
        print("✅ Column user_id already exists. Nothing to do.")
        return

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE analysis_logs ADD COLUMN user_id INTEGER"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_analysis_logs_user_id ON analysis_logs(user_id)"))

    print("✅ Added user_id column + index to analysis_logs.")

if __name__ == "__main__":
    main()
