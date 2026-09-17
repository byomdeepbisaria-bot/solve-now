from fastapi import Depends, HTTPException, status, Request
from jose import jwt, JWTError
from pydantic import ValidationError
from sqlalchemy.orm import Session
import uuid

from core.config import settings
from core.database import get_db
from models.user import User

def get_token_from_cookie(request: Request) -> str:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    if token.startswith("Bearer "):
        token = token[7:]
    return token

def get_token_optional(request: Request) -> str | None:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        return None
    if token.startswith("Bearer "):
        token = token[7:]
    return token

def get_current_user_optional(
    db: Session = Depends(get_db), token: str | None = Depends(get_token_optional)
) -> User | None:
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=["HS256"]
        )
        token_data = payload.get("sub")
        if token_data is None:
            return None
    except (JWTError, ValidationError):
        return None
        
    from models.security import TokenDenylist
    denied_token = db.query(TokenDenylist).filter(TokenDenylist.token == token).first()
    if denied_token:
        return None

    try:
        user_uuid = uuid.UUID(token_data)
    except (ValueError, AttributeError):
        return None
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        return None
    if not user.is_active:
        return None
    return user

def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(get_token_from_cookie)
) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=["HS256"]
        )
        token_data = payload.get("sub")
        if token_data is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    from models.security import TokenDenylist
    denied_token = db.query(TokenDenylist).filter(TokenDenylist.token == token).first()
    if denied_token:
        raise HTTPException(status_code=401, detail="Token has been revoked")

    try:
        user_uuid = uuid.UUID(token_data)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail="Invalid token subject")
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user

def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role and current_user.role.name == "ADMIN":
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="The user doesn't have enough privileges"
    )
