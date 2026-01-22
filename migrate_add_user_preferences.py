# migrate_add_user_preferences.py
from sqlalchemy import text, inspect
from db import engine

def main():
    inspector = inspect(engine)
    cols = [c["name"] for c in inspector.get_columns("users")]

    statements = []

    if "preferred_language" not in cols:
        statements.append(
            "ALTER TABLE users ADD COLUMN preferred_language TEXT NOT NULL DEFAULT 'english'"
        )

    if "preferred_difficulty" not in cols:
        statements.append(
            "ALTER TABLE users ADD COLUMN preferred_difficulty TEXT NOT NULL DEFAULT 'moderate'"
        )

    if not statements:
        print("✅ Preference columns already exist. Nothing to do.")
        return

    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))

    print("✅ Added missing preference columns to users.")

if __name__ == "__main__":
    main()
