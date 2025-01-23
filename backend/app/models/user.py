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
from sqlalchemy.sql import func
from ..database import Base
import uuid


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    google_token = Column(String, nullable=True)
    google_refresh_token = Column(String, nullable=True)
    token_expiry = Column(DateTime, nullable=True)
