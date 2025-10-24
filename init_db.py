from db import engine, Base
from models import AnalysisLog  # ensures the model is registered

def main():
    # Create all tables defined on Base metadata (includes AnalysisLog)
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created.")

if __name__ == "__main__":
    main()
