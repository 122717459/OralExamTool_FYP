#dotenv and load_dotenv I learned from ChatGPT
from dotenv import load_dotenv #Helper library that reads .env files
import os

# Load all variables from the .env  file
load_dotenv()


class Settings:
    """
    Central place for app configuration.
    Pulls values from .env and provides safe defaults.
    """

    # ---------------- Database ----------------
    raw_db = os.getenv("DATABASE_URL", "sqlite:///oralexamtool.db")
    if raw_db.startswith("postgres://"):
        raw_db = raw_db.replace("postgres://", "postgresql://", 1)
    DATABASE_URL = raw_db

    # ---------------- OpenAI (standard) ----------------
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # ---------------- Azure OpenAI (optional) ----------------
    # These are optional; if not set, the code will fall back to standard OpenAI.
    AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
    AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
    AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-this")
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    PORT = int(os.getenv("PORT", "5000"))

# Create a global instance we can import anywhere in the app
settings = Settings()
