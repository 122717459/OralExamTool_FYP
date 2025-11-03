# Import the tools we need from SQLAlchemy
# - create_engine: actually connects us to the database
# - sessionmaker: makes "Session" objects for reading/writing data
# - declarative_base: base class all our models will inherit from
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Import your app settings (this is where DATABASE_URL is stored)
from config import settings


# ------------------------------------------------------------
# Create the database engine
# ------------------------------------------------------------
# The engine is the "core" connection to your database.
# It knows where your database lives (from DATABASE_URL in .env)
# and handles the low-level connection details.
#
# echo=False means: don’t print SQL statements in the console.
# future=True just tells SQLAlchemy to use the modern 2.x-style API.
engine = create_engine(settings.DATABASE_URL, echo=False, future=True)


# ------------------------------------------------------------
# Create a Session factory
# ------------------------------------------------------------
# This is how you’ll actually interact with the database in code.
# Each time you need to read/write data, you create a new Session from this.
#
# - bind=engine → connects it to the engine we made above
# - autoflush=False → avoids automatically sending changes until you commit
# - autocommit=False → you control when to commit (good for transactions)
# - future=True → again, uses the newer API style
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


# ------------------------------------------------------------
# Create a Base class for models
# ------------------------------------------------------------
# Every model (table) class in your app should inherit from this Base.
# It helps SQLAlchemy know which classes map to database tables.
Base = declarative_base()


# ------------------------------------------------------------
# Dependency generator for database sessions
# ------------------------------------------------------------
# This is a little helper function that “yields” a database session.
# It’s commonly used with FastAPI or Flask so you can get a fresh session
# in each request and make sure it closes automatically afterwards.
def get_db():
    """
    Example use:
        db = SessionLocal()
        try:
            # do stuff with db (query, insert, etc.)
        finally:
            db.close()
    """
    db = SessionLocal()
    try:
        # give the session to whoever called this function
        yield db
    finally:
        # no matter what happens (error or success), close the connection
        db.close()
