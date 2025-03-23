"""
User Database Model -- Uses SQLAlchemy models for database structure (just stores the data. validation of email happens in schemas/user.py)
Defines user table structure and fields:
- Basic info (id, email)
- Authentication (password hash)
- OAuth data (Google tokens)
- Account status
- Timestamps
"""

from sqlalchemy import Boolean, Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime, timezone


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    # Add relationships
    oauth_credentials = relationship(
        "OAuthCredentials", back_populates="user", cascade="all, delete-orphan"
    )
    oauth_states = relationship(
        "OAuthState", back_populates="user", cascade="all, delete-orphan"
    )
