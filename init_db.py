from db import engine, Base
from models import AnalysisLog  # ensures the model is registered

def main():
    # Create all tables defined on Base metadata (includes AnalysisLog)
    Base.metadata.create_all(bind=engine) # Looks at every model registered under base, and makes sure a corresponding table exists in the connected database
    print("✅ Database tables created.")

if __name__ == "__main__":
    main()
