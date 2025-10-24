from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

# Create the database engine (SQLite file set in .env)
engine = create_engine(settings.DATABASE_URL, echo=False, future=True)

# Session factory (you'll use this to talk to the DB)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Base class for models to inherit from
Base = declarative_base()

def get_db():
    """
    Usage pattern:
        db = SessionLocal()
        try:
            # use db here
        finally:
            db.close()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
