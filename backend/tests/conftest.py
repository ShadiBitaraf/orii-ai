import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.models.user import User
from app.utils.security import get_password_hash

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test.db"
engine_test = create_engine(SQLALCHEMY_TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(bind=engine_test)


@pytest.fixture
def test_db():
    """Create test database, yield it for tests, then cleanup"""
    Base.metadata.create_all(bind=engine_test)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture
def client(test_db):
    """Create FastAPI test client with test database"""
    app.dependency_overrides[get_db] = lambda: test_db
    return TestClient(app)


@pytest.fixture
def test_user(test_db):
    """Create test user in database"""
    user = User(
        email="test@example.com", hashed_password=get_password_hash("testpassword")
    )
    test_db.add(user)
    test_db.commit()
    return user
