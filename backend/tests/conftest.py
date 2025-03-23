import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.models.user import User
from app.models.oauth_credentials import OAuthCredentials
from app.models.oauth_state import OAuthState  
from app.utils.security import get_password_hash, create_access_token
from datetime import datetime, timedelta
import logging

# Configure test logging (commented out debug logging)
# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)

# Use test database URL for testing environment
SQLALCHEMY_TEST_DATABASE_URL = "postgresql://orii_user:password@localhost/orii_test_db"
engine_test = create_engine(SQLALCHEMY_TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


@pytest.fixture(scope="session")
def test_app():
    """Creates and returns the FastAPI test application for testing"""
    # List routes in the app (commented out debug print)
    # logger.info("Test application routes:")
    # for route in app.routes:
    #     if hasattr(route, "methods"):
    #         logger.info(f"{route.methods} {route.path}")
    return app


@pytest.fixture(scope="function")
def test_db():
    """Creates and sets up the test database tables, then cleans up after test"""
    # Drop all tables first to ensure clean state
    Base.metadata.drop_all(bind=engine_test)
    # Setup database tables and provide session for each test
    Base.metadata.create_all(bind=engine_test)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Clean up tables after test
        Base.metadata.drop_all(bind=engine_test)


@pytest.fixture
def client(test_app, test_db):
    """Creates the test client with overridden database dependency"""

    # Override the database dependency to use test database
    def override_get_db():
        try:
            yield test_db
        finally:
            test_db.rollback()

    test_app.dependency_overrides[get_db] = override_get_db
    client = TestClient(test_app)
    # logger.info("Test client created with database override")  # Debug log commented out
    return client


@pytest.fixture
def test_user(test_db):
    """Creates a test user in the database"""
    # Creating and returning a test user for authentication tests
    user = User(
        email="test@example.com",
        hashed_password=get_password_hash("testpassword"),
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_user_with_oauth(test_db, test_user):
    """Creates a test user with OAuth credentials in the database"""
    # Setting up OAuth credentials for the test user
    oauth = OAuthCredentials(
        user_id=test_user.id,
        provider="google",
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        token_expiry=datetime.utcnow() + timedelta(hours=1),
    )
    test_db.add(oauth)
    test_db.commit()
    test_db.refresh(oauth)
    return {"user": test_user, "oauth": oauth}


@pytest.fixture
def authenticated_client(client, test_user):
    """Creates an authenticated test client with an access token"""
    # Creating a valid access token for the test user
    access_token = create_access_token(
        data={"sub": test_user.email}, expires_delta=timedelta(minutes=30)
    )
    return {"client": client, "token": access_token, "user": test_user}
    
@pytest.fixture(autouse=True)
def clear_sqlalchemy_metadata():
    """Clear SQLAlchemy metadata before each test"""
    Base.metadata.clear()
    yield


# Add debug print at import time (commented out for production)
# print("\nRegistered routes in test environment:")
# for route in app.routes:
#     if hasattr(route, "methods"):
#         print(f"{route.methods} {route.path}")
