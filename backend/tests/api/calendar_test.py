import pytest
from unittest.mock import patch, MagicMock
import logging
from datetime import datetime, timedelta
from app.models.oauth_state import OAuthState

# Configure test logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.fixture
def mock_google_auth():
    """Mock Google's OAuth flow for testing the authentication initiation"""
    with patch("app.api.calendar.Flow") as mock_flow:
        mock_instance = MagicMock()
        mock_instance.authorization_url.return_value = (
            "https://mock-google-auth.com",
            "test-state",
        )
        mock_flow.from_client_config.return_value = mock_instance
        yield mock_instance


def test_google_auth_initiation(mock_google_auth, authenticated_client, test_db):
    """Test the initiation of the Google OAuth flow"""
    logger.info("Testing Google auth initiation")

    # Commented out debug output for routes
    # print("\nAvailable routes:")
    # for route in authenticated_client["client"].app.routes:
    #     print(f"  {route.methods} {route.path}")

    response = authenticated_client["client"].get(
        "/api/auth/google",
        headers={"Authorization": f"Bearer {authenticated_client['token']}"},
        follow_redirects=False,
    )

    # Commented out debug output for request details
    # print(f"\nRequest URL: /api/auth/google")
    # print(f"Response status: {response.status_code}")
    # print(f"Response body: {response.text}")

    # Assert the response status and location header for OAuth redirect
    assert response.status_code == 307
    assert "mock-google-auth.com" in response.headers["location"]


@pytest.mark.asyncio
async def test_oauth_callback(authenticated_client, test_db):
    """Test the handling of the OAuth callback"""
    logger.info("Testing OAuth callback")

    # Create an OAuthState for testing
    state = OAuthState(
        user_id=authenticated_client["user"].id,
        state="test-state",
        expires_at=datetime.utcnow() + timedelta(minutes=5),
    )
    test_db.add(state)
    test_db.commit()

    # Mock the OAuth flow for the callback
    with patch("app.api.calendar.Flow") as mock_flow:
        mock_instance = MagicMock()
        mock_instance.fetch_token.return_value = None
        mock_instance.credentials.token = "test_token"
        mock_instance.credentials.refresh_token = "test_refresh"
        mock_instance.credentials.expiry = datetime.utcnow() + timedelta(hours=1)
        mock_flow.from_client_config.return_value = mock_instance

        response = authenticated_client["client"].get(
            "/api/oauth/callback",
            params={"code": "test-code", "state": "test-state"},
            headers={"Authorization": f"Bearer {authenticated_client['token']}"},
        )

        # Assert the callback response status
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_events(authenticated_client, test_user_with_oauth, test_db):
    """Test the listing of calendar events"""
    logger.info("Testing list events")

    # Commented out debug output for OAuth token and user ID
    # print(f"\nUser ID: {test_user_with_oauth['user'].id}")
    # print(f"OAuth token: {test_user_with_oauth['oauth'].access_token}")

    # Mock the Google Calendar API response
    with patch("app.api.calendar.build") as mock_build:
        mock_service = MagicMock()
        mock_events = {
            "items": [
                {
                    "id": "1",
                    "summary": "Test Meeting",
                    "start": {"dateTime": "2024-01-28T10:00:00Z"},
                    "end": {"dateTime": "2024-01-28T11:00:00Z"},
                }
            ]
        }
        mock_service.events().list().execute.return_value = mock_events
        mock_build.return_value = mock_service

        response = authenticated_client["client"].get(
            "/api/calendar/events",
            headers={"Authorization": f"Bearer {authenticated_client['token']}"},
        )

        # Commented out debug output for response details
        # print(f"Response status: {response.status_code}")
        # print(f"Response body: {response.text}")

        # Assert the response status and validate events list
        assert response.status_code == 200
        events = response.json()
        assert len(events) == 1
        assert events[0]["summary"] == "Test Meeting"
