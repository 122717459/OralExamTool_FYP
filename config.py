from dotenv import load_dotenv
import os

# Load all variables from the .env file
load_dotenv()

# This class stores configuration settings for the project
class Settings:
    # Database connection
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///oralexamtool.db")

    # OpenAI configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # Azure OpenAI configuration (optional)
    AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
    AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
    AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")

# Create an instance we can import in other files
settings = Settings()
#print("Database URL:", settings.DATABASE_URL)
#print("OpenAI Key found:", bool(settings.OPENAI_API_KEY))
