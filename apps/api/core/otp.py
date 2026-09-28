import secrets
import hashlib
import hmac


def generate_otp_code() -> str:
    """
    Generate a cryptographically secure 6-digit numeric OTP string.
    e.g. '048291', '920145'
    """
    num = secrets.randbelow(1000000)
    return f"{num:06d}"


def hash_otp(code: str) -> str:
    """
    Hash an OTP code using SHA-256 before database storage.
    OTP is NEVER stored as plaintext in the database or logs.
    """
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def verify_otp(submitted_code: str, stored_hash: str) -> bool:
    """
    Verify a submitted OTP against the stored SHA-256 hash
    using constant-time comparison to prevent timing attacks.
    """
    computed = hash_otp(submitted_code)
    return hmac.compare_digest(computed, stored_hash)


def generate_reset_token() -> str:
    """
    Generate a cryptographically secure, single-use password reset token.
    Issued upon successful 6-digit OTP verification.
    """
    return secrets.token_urlsafe(32)
