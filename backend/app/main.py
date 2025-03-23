from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import Any

# import logging
# import sys

from app.database import Base, engine, get_db
from app.models import user as models
from app.schemas import user as schemas
from app.utils.security import (
    verify_password,
    create_access_token,
    get_current_user,
    get_password_hash,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from app.api import calendar
from app.core.config import get_settings

# Configure comprehensive logging (commented out for debugging purposes)
# logging.basicConfig(
#     level=logging.DEBUG,
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
#     stream=sys.stdout,
# )
# logger = logging.getLogger(__name__)

# Get settings (settings are fetched for environment-specific configuration)
settings = get_settings()

# Create database tables (ensures the database schema is created)
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app (defines the API's metadata and settings)
app = FastAPI(
    title="ORII Calendar Assistant",
    description="Calendar Assistant API with Google Calendar Integration",
    version="1.0.0",
    debug=True,
)

# Add CORS middleware (handles cross-origin requests for client apps)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Debug middleware to log all requests (commented out for debugging purposes)
# @app.middleware("http")
# async def log_requests(request: Request, call_next):
#     logger.debug(f"Request path: {request.url.path}")
#     logger.debug(f"Request method: {request.method}")
#     logger.debug(f"Request headers: {request.headers}")
#     response = await call_next(request)
#     logger.debug(f"Response status: {response.status_code}")
#     return response


# Print debug info on startup (commented out for debugging purposes)
# @app.on_event("startup")
# async def startup_event():
#     logger.info("Starting ORII Calendar Assistant")
#     logger.info(f"Environment: {settings.ENV}")
#     logger.info("Registered routes:")
#     route_groups = {}
#     for route in app.routes:
#         if hasattr(route, "tags"):
#             tag = route.tags[0] if route.tags else "untagged"
#         else:
#             tag = "untagged"
#         if tag not in route_groups:
#             route_groups[tag] = []
#         route_info = {
#             "path": route.path,
#             "methods": list(route.methods) if hasattr(route, "methods") else ["ANY"],
#             "name": route.name if hasattr(route, "name") else None,
#             "endpoint": route.endpoint.__name__ if hasattr(route, "endpoint") else None,
#         }
#         route_groups[tag].append(route_info)
#     for tag, routes in route_groups.items():
#         logger.info(f"\n{tag.upper()} Routes:")
#         for route in routes:
#             logger.info(f"  {', '.join(route['methods'])} {route['path']}")
#             if route["endpoint"]:
#                 logger.info(f"    → {route['endpoint']}")


# Add test routes for debugging (commented out for debugging purposes)
# @app.get("/api/test", tags=["test"])
# async def test_route():
#     """Test endpoint to verify API is working"""
#     return {
#         "status": "ok",
#         "environment": settings.ENV,
#         "registered_routes": [
#             {"path": route.path, "methods": route.methods}
#             for route in app.routes
#             if hasattr(route, "methods")
#         ],
#     }


# Include the calendar router (handles the calendar-related routes)
# logger.info("Registering calendar routes...")
app.include_router(
    calendar.router,
    prefix="",  # No prefix needed as routes include /api
    tags=["calendar"],
)
# logger.info("Calendar routes registered")


# User management endpoints
@app.post(
    "/api/users/",
    response_model=schemas.UserOut,
    status_code=status.HTTP_201_CREATED,
    tags=["users"],
)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)) -> Any:
    """Create new user"""
    # logger.debug(f"Creating new user with email: {user.email}")
    try:
        # Check if user already exists
        db_user = db.query(models.User).filter(models.User.email == user.email).first()
        if db_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
        # Create new user
        db_user = models.User(
            email=user.email, hashed_password=get_password_hash(user.password)
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        # logger.info(f"User created successfully: {user.email}")
        return db_user
    except Exception as e:
        # logger.error(f"Error creating user: {str(e)}")
        raise


@app.post("/api/token", response_model=schemas.Token, tags=["auth"])
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> Any:
    """OAuth2 compatible token login"""
    # logger.debug(f"Login attempt for user: {form_data.username}")
    try:
        # Verify user's credentials
        user = (
            db.query(models.User)
            .filter(models.User.email == form_data.username)
            .first()
        )
        if not user or not verify_password(form_data.password, user.hashed_password):
            # logger.warning(f"Failed login attempt for user: {form_data.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Generate access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email}, expires_delta=access_token_expires
        )
        # logger.info(f"Successful login for user: {form_data.username}")
        return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        # logger.error(f"Error during login: {str(e)}")
        raise


@app.get("/api/users/me", response_model=schemas.UserOut, tags=["users"])
def read_current_user(current_user: models.User = Depends(get_current_user)) -> Any:
    """Get current user"""
    # logger.debug(f"Fetching current user: {current_user.email}")
    return current_user


# Health check endpoint (used for checking the API health)
@app.get("/api/health", tags=["system"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "env": settings.ENV,
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn

    # logger.info("Starting development server...")
    uvicorn.run(
        "app.main:app", host="127.0.0.1", port=8000, reload=True, log_level="debug"
    )
