from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import create_access_token, get_password_hash, verify_password
from core.config import settings
from models.user import User
from schemas.user import UserCreate, UserLogin, UserResponse
from api.deps import get_current_user

router = APIRouter()

@router.post("/register", response_model=UserResponse)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="The user with this email already exists in the system.")

    # Derive username from input or fall back to email prefix
    desired_username = user_in.username or user_in.email.split("@")[0]
    # Ensure username uniqueness — append suffix if taken
    base = desired_username
    suffix = 1
    while db.query(User).filter(User.username == desired_username).first():
        desired_username = f"{base}{suffix}"
        suffix += 1

    hashed_password = get_password_hash(user_in.password)
    db_user = User(
        email=user_in.email,
        username=desired_username,
        hashed_password=hashed_password,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.post("/login")
def login(request: Request, response: Response, user_in: UserLogin, db: Session = Depends(get_db)):
    from services.audit import log_audit_event
    user = db.query(User).filter(User.email == user_in.email).first()
    
    if not user or not verify_password(user_in.password, user.hashed_password):
        log_audit_event(db, "AUTH_FAILED", f"Failed login for {user_in.email}", ip_address=request.client.host if request.client else None)
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not user.is_active:
        log_audit_event(db, "AUTH_FAILED_INACTIVE", f"Login attempt on inactive user {user_in.email}", ip_address=request.client.host if request.client else None)
        raise HTTPException(status_code=400, detail="Inactive user")
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=str(user.id), expires_delta=access_token_expires
    )
    
    # Set HttpOnly cookie - only set secure=True in production (HTTPS)
    is_secure = settings.is_production
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=int(access_token_expires.total_seconds()),
    )
    
    return {
        "message": "Successfully logged in",
        "access_token": access_token,
        "token_type": "bearer"
    }

from api.deps import get_current_user, get_token_from_cookie

@router.post("/logout")
def logout(
    response: Response, 
    token: str = Depends(get_token_from_cookie),
    db: Session = Depends(get_db)
):
    from models.security import TokenDenylist
    denied = TokenDenylist(token=token)
    db.add(denied)
    db.commit()
    
    response.delete_cookie("access_token")
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
