import pytest
import os
from dotenv import load_dotenv

load_dotenv()


def test_environment_variables():
    """Test if all required env variables are set"""
    assert os.getenv("DATABASE_URL") is not None
    assert os.getenv("TEST_DATABASE_URL") is not None
    assert os.getenv("JWT_SECRET") is not None


def test_database_connection():
    """Test database connection"""
    from backend.app.database import engine
    from sqlalchemy import text

    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
