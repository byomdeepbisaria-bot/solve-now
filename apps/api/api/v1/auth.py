from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc

from core.database import get_db
from core.security import create_access_token, get_password_hash, verify_password
from core.config import settings
from core.otp import generate_otp_code, hash_otp, verify_otp, generate_reset_token
from models.user import User
from models.auth_otp import AuthOTP
from services.email import send_verification_otp, send_password_reset_otp
from schemas.user import (
    UserCreate,
    UserLogin,
    UserResponse,
    VerifyEmailOTP,
    ResendOTPRequest,
    ForgotPasswordRequest,
    VerifyResetOTPRequest,
    ResetPasswordRequest,
)
from api.deps import get_current_user, get_token_from_cookie

router = APIRouter()


@router.post("/register", response_model=UserResponse)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )

    # Derive username from input or fall back to email prefix
    desired_username = user_in.username or user_in.email.split("@")[0]
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
        is_verified=False,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # Generate 6-digit OTP for email verification
    raw_otp = generate_otp_code()
    hashed_otp = hash_otp(raw_otp)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    otp_record = AuthOTP(
        user_id=db_user.id,
        email=db_user.email,
        purpose="email_verification",
        otp_hash=hashed_otp,
        expires_at=expires_at,
    )
    db.add(otp_record)
    db.commit()

    # Send verification email via Gmail API / SMTP
    send_verification_otp(db_user.email, raw_otp)

    return db_user


@router.post("/verify-email")
def verify_email(payload: VerifyEmailOTP, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid verification request.")

    if user.is_verified:
        return {"message": "Email is already verified. You may log in."}

    now = datetime.now(timezone.utc)
    otp_record = (
        db.query(AuthOTP)
        .filter(
            AuthOTP.email == payload.email,
            AuthOTP.purpose == "email_verification",
            AuthOTP.is_used == False,
        )
        .order_by(desc(AuthOTP.created_at))
        .first()
    )

    if not otp_record:
        raise HTTPException(
            status_code=400, detail="No active verification code found. Please resend code."
        )

    if otp_record.expires_at < now:
        raise HTTPException(
            status_code=400, detail="Verification code has expired. Please request a new code."
        )

    if otp_record.attempt_count >= otp_record.max_attempts:
        otp_record.is_used = True
        db.commit()
        raise HTTPException(
            status_code=400, detail="Too many failed attempts. Please request a new code."
        )

    otp_record.attempt_count += 1

    if not verify_otp(payload.otp, otp_record.otp_hash):
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid verification code.")

    # Success
    otp_record.is_used = True
    user.is_verified = True
    db.commit()

    return {"message": "Email verified successfully. You may now log in."}


@router.post("/resend-otp")
def resend_otp(payload: ResendOTPRequest, db: Session = Depends(get_db)):
    purpose = payload.purpose
    if purpose not in ("email_verification", "password_reset"):
        raise HTTPException(status_code=400, detail="Invalid OTP purpose.")

    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        return {
            "message": "If an account exists for this email, a verification code has been sent."
        }

    if purpose == "email_verification" and user.is_verified:
        return {"message": "Email is already verified."}

    now = datetime.now(timezone.utc)
    last_otp = (
        db.query(AuthOTP)
        .filter(AuthOTP.email == payload.email, AuthOTP.purpose == purpose)
        .order_by(desc(AuthOTP.created_at))
        .first()
    )

    # 60-second cooldown check
    if last_otp and last_otp.last_sent_at:
        elapsed = (now - last_otp.last_sent_at).total_seconds()
        if elapsed < 60:
            remaining = int(60 - elapsed)
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {remaining} seconds before requesting another code.",
            )

    # Invalidate previous active OTPs for email & purpose
    db.query(AuthOTP).filter(
        AuthOTP.email == payload.email,
        AuthOTP.purpose == purpose,
        AuthOTP.is_used == False,
    ).update({"is_used": True})

    raw_otp = generate_otp_code()
    hashed_otp = hash_otp(raw_otp)
    expires_at = now + timedelta(minutes=10)

    new_otp = AuthOTP(
        user_id=user.id,
        email=user.email,
        purpose=purpose,
        otp_hash=hashed_otp,
        expires_at=expires_at,
    )
    db.add(new_otp)
    db.commit()

    if purpose == "email_verification":
        send_verification_otp(user.email, raw_otp)
    else:
        send_password_reset_otp(user.email, raw_otp)

    return {
        "message": "If an account exists for this email, a verification code has been sent."
    }


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    generic_msg = {
        "message": "If an account exists for this email, a 6-digit reset code has been sent."
    }

    if not user:
        return generic_msg

    now = datetime.now(timezone.utc)
    last_otp = (
        db.query(AuthOTP)
        .filter(AuthOTP.email == payload.email, AuthOTP.purpose == "password_reset")
        .order_by(desc(AuthOTP.created_at))
        .first()
    )

    if last_otp and last_otp.last_sent_at:
        elapsed = (now - last_otp.last_sent_at).total_seconds()
        if elapsed < 60:
            return generic_msg

    db.query(AuthOTP).filter(
        AuthOTP.email == payload.email,
        AuthOTP.purpose == "password_reset",
        AuthOTP.is_used == False,
    ).update({"is_used": True})

    raw_otp = generate_otp_code()
    hashed_otp = hash_otp(raw_otp)
    expires_at = now + timedelta(minutes=10)

    new_otp = AuthOTP(
        user_id=user.id,
        email=user.email,
        purpose="password_reset",
        otp_hash=hashed_otp,
        expires_at=expires_at,
    )
    db.add(new_otp)
    db.commit()

    send_password_reset_otp(user.email, raw_otp)

    return generic_msg


@router.post("/verify-reset-otp")
def verify_reset_otp(payload: VerifyResetOTPRequest, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    otp_record = (
        db.query(AuthOTP)
        .filter(
            AuthOTP.email == payload.email,
            AuthOTP.purpose == "password_reset",
            AuthOTP.is_used == False,
        )
        .order_by(desc(AuthOTP.created_at))
        .first()
    )

    if not otp_record:
        raise HTTPException(
            status_code=400, detail="No active password reset code found. Please request a new code."
        )

    if otp_record.expires_at < now:
        raise HTTPException(
            status_code=400, detail="Password reset code has expired. Please request a new code."
        )

    if otp_record.attempt_count >= otp_record.max_attempts:
        otp_record.is_used = True
        db.commit()
        raise HTTPException(
            status_code=400, detail="Too many failed attempts. Please request a new code."
        )

    otp_record.attempt_count += 1

    if not verify_otp(payload.otp, otp_record.otp_hash):
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid 6-digit code.")

    # Issue single-use reset token valid for 15 minutes
    reset_token = generate_reset_token()
    otp_record.is_used = True
    otp_record.reset_token = reset_token
    otp_record.reset_token_expires_at = now + timedelta(minutes=15)
    db.commit()

    return {
        "message": "Reset code verified successfully.",
        "reset_token": reset_token,
    }


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    if len(payload.new_password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters long."
        )

    now = datetime.now(timezone.utc)
    otp_record = (
        db.query(AuthOTP)
        .filter(
            AuthOTP.reset_token == payload.reset_token,
            AuthOTP.reset_token_expires_at > now,
        )
        .first()
    )

    if not otp_record:
        raise HTTPException(
            status_code=400, detail="Invalid or expired reset authorization token."
        )

    user = db.query(User).filter(User.id == otp_record.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="User account not found.")

    # Update password
    user.hashed_password = get_password_hash(payload.new_password)

    # Invalidate reset token and all OTPs for user
    otp_record.reset_token = None
    db.query(AuthOTP).filter(AuthOTP.email == user.email).update({"is_used": True})

    db.commit()

    return {"message": "Password reset successfully. You may now log in with your new password."}


@router.post("/login")
def login(
    request: Request,
    response: Response,
    user_in: UserLogin,
    db: Session = Depends(get_db),
):
    from services.audit import log_audit_event

    user = db.query(User).filter(User.email == user_in.email).first()

    if not user or not verify_password(user_in.password, user.hashed_password):
        log_audit_event(
            db,
            "AUTH_FAILED",
            f"Failed login for {user_in.email}",
            ip_address=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not user.is_active:
        log_audit_event(
            db,
            "AUTH_FAILED_INACTIVE",
            f"Login attempt on inactive user {user_in.email}",
            ip_address=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=str(user.id), expires_delta=access_token_expires
    )

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
        "token_type": "bearer",
    }


@router.post("/logout")
def logout(
    response: Response,
    token: str = Depends(get_token_from_cookie),
    db: Session = Depends(get_db),
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
