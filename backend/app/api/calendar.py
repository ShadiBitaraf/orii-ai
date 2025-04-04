from fastapi import APIRouter, HTTPException, Depends, Request, status
from fastapi.responses import RedirectResponse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.oauth_credentials import OAuthCredentials
from app.models.oauth_state import OAuthState
from app.utils.security import get_current_user
from app.models.user import User
from datetime import datetime, timedelta, timezone
from app.core.config import get_settings
from app.utils.logger import setup_logger

# Initialize settings and logging
settings = get_settings()
logger = setup_logger("app.api.calendar")

# Create router with explicit tags and prefix
router = APIRouter(
    tags=["calendar"],
)

# Define OAuth scopes
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


def create_flow(redirect_uri: str) -> Flow:
    """Creates an OAuth 2.0 flow instance.

    This function initializes the OAuth flow using the client configuration
    and specified redirect URI, returning a Flow object that can be used to
    authenticate the user and obtain access tokens.
    """
    try:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=SCOPES,
            redirect_uri=redirect_uri,
        )
        return flow
    except Exception as e:
        logger.error(f"Error creating flow: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize OAuth flow",
        )


@router.get("/api/auth/google")
async def google_auth(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Initiates Google OAuth flow.

    This endpoint begins the OAuth process by redirecting the user to the Google
    OAuth consent screen where they can grant access to their Google Calendar.
    The state is stored in the database for security purposes.
    """
    logger.debug(f"google_auth endpoint called by user {current_user.id}")
    try:
        # Create flow using the redirect URI from settings
        flow = create_flow(settings.REDIRECT_URI)

        # Get authorization URL and state
        authorization_url, state = flow.authorization_url(
            access_type="offline", include_granted_scopes="true", prompt="consent"
        )

        # Store state in database
        oauth_state = OAuthState(
            user_id=current_user.id,
            state=state,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        db.add(oauth_state)
        db.commit()

        logger.debug(f"Redirecting to: {authorization_url}")
        return RedirectResponse(
            authorization_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )

    except Exception as e:
        logger.error(f"Error in google_auth: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/api/oauth/callback")
async def oauth_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Handles the OAuth callback.

    This endpoint is called after the user has authorized the application. It
    exchanges the authorization code for an access token and stores the credentials.
    """
    logger.debug(f"oauth_callback called for user {current_user.id}")

    # Verify state
    stored_state = (
        db.query(OAuthState)
        .filter(
            OAuthState.user_id == current_user.id,
            OAuthState.state == state,
            OAuthState.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )

    if not stored_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired state"
        )

    try:
        # Create flow and fetch token
        flow = create_flow(settings.REDIRECT_URI)
        flow.fetch_token(code=code)

        # Update or create credentials
        oauth_cred = (
            db.query(OAuthCredentials)
            .filter(
                OAuthCredentials.user_id == current_user.id,
                OAuthCredentials.provider == "google",
            )
            .first()
        )

        if oauth_cred:
            oauth_cred.access_token = flow.credentials.token
            oauth_cred.refresh_token = flow.credentials.refresh_token
            oauth_cred.token_expiry = flow.credentials.expiry
        else:
            oauth_cred = OAuthCredentials(
                user_id=current_user.id,
                provider="google",
                access_token=flow.credentials.token,
                refresh_token=flow.credentials.refresh_token,
                token_expiry=flow.credentials.expiry,
            )
            db.add(oauth_cred)

        # Clean up and commit
        db.delete(stored_state)
        db.commit()

        return {"message": "Successfully authenticated with Google Calendar"}

    except Exception as e:
        logger.error(f"Error in oauth_callback: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/api/calendar/events")
async def list_events(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    start_date: str = None,
    end_date: str = None,
):
    """Lists calendar events using stored credentials.

    This endpoint retrieves upcoming calendar events for the authenticated user.
    The user must have previously authenticated with Google and provided access
    to their Google Calendar. Optionally, a date range can be specified.
    """
    logger.debug(f"list_events called for user {current_user.id}")

    try:
        # Get credentials
        credentials = (
            db.query(OAuthCredentials)
            .filter(
                OAuthCredentials.user_id == current_user.id,
                OAuthCredentials.provider == "google",
            )
            .first()
        )

        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No Google Calendar credentials found. Please authenticate first.",
            )

        # Build Google credentials
        google_creds = Credentials(
            token=credentials.access_token,
            refresh_token=credentials.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=SCOPES,
        )

        # Build service and get events
        service = build("calendar", "v3", credentials=google_creds)

        time_min = start_date or datetime.now(timezone.utc).isoformat()
        if not time_min.endswith("Z"):
            time_min += "Z"

        params = {
            "calendarId": "primary",
            "timeMin": time_min,
            "maxResults": 10,
            "singleEvents": True,
            "orderBy": "startTime",
        }

        if end_date:
            params["timeMax"] = end_date if end_date.endswith("Z") else end_date + "Z"

        events_result = service.events().list(**params).execute()
        return events_result.get("items", [])

    except Exception as e:
        logger.error(f"Error in list_events: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
