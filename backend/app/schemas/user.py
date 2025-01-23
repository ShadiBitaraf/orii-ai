"""
Data Validation Models -- Uses Pydantic models for I/O validation (valides email format)
Pydantic models for:
- User creation/updates
- Authentication requests
- API responses
- Token handling
Ensures data validation and serialization.
"""

from pydantic import BaseModel, EmailStr, field_validator, ConfigDict, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    email: EmailStr  # Validates email format
    password: str = Field(
        ..., min_length=8
    )  # Password must be 8+ chars. instead of using constr(min_length=8) directly as a type, used Field from Pydantic, which allows to define constraints as part of the field metadata.

    @field_validator("password")
    def password_strength(cls, v):
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one number")
        if not any(char.isupper() for char in v):
            raise ValueError("Password must contain at least one uppercase letter")
        return v
    


class UserLogin(UserBase):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


class UserOut(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )  # Allows conversion from SQLAlchemy model


class GoogleToken(BaseModel):
    access_token: str
    refresh_token: str
    token_expiry: datetime
