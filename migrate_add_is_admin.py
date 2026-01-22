# migrate_add_is_admin.py
from sqlalchemy import text, inspect
from db import engine

def main():
    inspector = inspect(engine)
    cols = [c["name"] for c in inspector.get_columns("users")]

    if "is_admin" in cols:
        print("✅ Column is_admin already exists. Nothing to do.")
        return

    with engine.begin() as conn:
        # SQLite stores booleans as 0/1 under the hood
        conn.execute(text("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"))

    print("✅ Added is_admin column to users (default = 0).")

if __name__ == "__main__":
    main()
