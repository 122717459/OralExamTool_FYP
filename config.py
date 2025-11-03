from dotenv import load_dotenv
import os

# Load all variables from the .env file
load_dotenv()


class Settings:
    """
    Central place for app configuration.
    Pulls values from .env and provides safe defaults.
    """

    # ---------------- Database ----------------
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///oralexamtool.db")

    # ---------------- OpenAI (standard) ----------------
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # ---------------- Azure OpenAI (optional) ----------------
    # These are optional; if not set, the code will fall back to standard OpenAI.
    AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
    AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
    AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")


# Create a global instance we can import anywhere
settings = Settings()
