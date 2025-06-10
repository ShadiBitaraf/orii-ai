"""
Database Connection Manager
Handles core database functionality:
- Database URL configuration
- SQLAlchemy engine setup
- Session management
- Connection dependency for FastAPI
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.app.core.config import get_settings

settings = get_settings()

# Get the database URL from settings
SQLALCHEMY_DATABASE_URL = settings.get_database_url()

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
