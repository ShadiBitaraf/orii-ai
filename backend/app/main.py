#when trying to test api requests, run uvicorn app.main:app --reload in backend/ not in main directory. 
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import Any
import uvicorn
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

Base.metadata.create_all(bind=engine)
app = FastAPI(title="ORII Calendar Assistant")


@app.post(
    "/api/users/", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED
)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)) -> Any:
    """Create new user"""
    # Check if user exists
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    # Create new user. and erro logging in endpoint for error 500.
    try:
        db_user = models.User(
            email=user.email, hashed_password=get_password_hash(user.password)
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except Exception as e:
        print(f"Error: {str(e)}")  # This will show in your uvicorn logs
        raise


@app.post("/api/token", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> Any:
    """OAuth2 compatible token login"""
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/api/users/me", response_model=schemas.UserOut)
def read_current_user(current_user: models.User = Depends(get_current_user)) -> Any:
    """Get current user"""
    return current_user


@app.post("/api/test-token", response_model=schemas.UserOut)
def test_token(current_user: models.User = Depends(get_current_user)) -> Any:
    """Test access token"""
    return current_user


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True, debug=True)
