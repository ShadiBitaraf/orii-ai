"""
Authentication System Tests

Comprehensive test suite for authentication functionality:
- User registration
- Login process
- Token generation
- Protected endpoint access
- Error cases (invalid credentials, etc.)

Tests cover both successful and failure scenarios to ensure
robust authentication handling.
"""

from fastapi import status
from backend.app.models.user import User
from backend.app.utils.security import get_password_hash


def test_create_user(client):
    response = client.post(
        "/api/users/",
        json={"email": "newuser@example.com", "password": "Strongpassword123"},
    )
    print("Response:", response.json())  # Debug validation error
    assert response.status_code == status.HTTP_201_CREATED


def test_login(client, test_user):
    response = client.post(
        "/api/token", data={"username": test_user.email, "password": "testpassword"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_password(client, test_user):
    response = client.post(
        "/api/token", data={"username": test_user.email, "password": "wrongpassword"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_current_user(client, test_user):
    # First login to get token
    login_response = client.post(
        "/api/token", data={"username": test_user.email, "password": "testpassword"}
    )
    token = login_response.json()["access_token"]

    # Use token to get current user
    response = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["email"] == test_user.email


# def test_db_contents(test_db):
#     """Print all users in test database"""
#     users = test_db.query(User).all()
#     for user in users:
#         print(f"ID: {user.id}, Email: {user.email}, Created: {user.created_at}")
