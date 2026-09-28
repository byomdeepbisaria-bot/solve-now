from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, Any
import uuid
from datetime import datetime


class UserBase(BaseModel):
    email: EmailStr


class UserLogin(UserBase):
    """Used only for the login endpoint — no username required."""
    password: str


class UserCreate(UserBase):
    """Used for registration — username is optional (falls back to email prefix)."""
    password: str
    username: Optional[str] = None


class UserResponse(UserBase):
    id: uuid.UUID
    username: Optional[str] = None
    is_active: bool
    is_verified: bool
    role: Optional[str] = None  # Serialized as role name string e.g. "ADMIN"
    created_at: datetime

    @field_validator("role", mode="before")
    @classmethod
    def extract_role_name(cls, v: Any) -> Optional[str]:
        """Accept either a Role ORM object or a plain string/None."""
        if v is None:
            return None
        if isinstance(v, str):
            return v
        # ORM Role object — extract .name
        return getattr(v, "name", None)

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str
