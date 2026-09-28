import os
import base64
import json
import logging
import smtplib
import urllib.request
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from core.config import settings

logger = logging.getLogger(__name__)


def _get_gmail_access_token() -> Optional[str]:
    """
    Obtain a fresh OAuth2 Access Token using GMAIL_REFRESH_TOKEN,
    GMAIL_CLIENT_ID, and GMAIL_CLIENT_SECRET via Google OAuth2 token endpoint.
    No local token.json file is required — works seamlessly in Render containers.
    """
    client_id = os.environ.get("GMAIL_CLIENT_ID") or getattr(settings, "GMAIL_CLIENT_ID", None)
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET") or getattr(settings, "GMAIL_CLIENT_SECRET", None)
    refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN") or getattr(settings, "GMAIL_REFRESH_TOKEN", None)

    if not (client_id and client_secret and refresh_token):
        return None

    client_id = str(client_id).strip().strip("'\"")
    client_secret = str(client_secret).strip().strip("'\"")
    refresh_token = str(refresh_token).strip().strip("'\"")

    url = "https://oauth2.googleapis.com/token"
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            return res_json.get("access_token")
    except Exception as e:
        logger.error(f"Gmail OAuth token refresh failed: {e}")
        return None


def _send_email_via_gmail_api(to_email: str, subject: str, html_content: str) -> bool:
    """
    Send an email via the Gmail REST API (v1) using an OAuth2 Access Token.
    """
    access_token = _get_gmail_access_token()
    if not access_token:
        return False

    sender_email = (
        os.environ.get("GMAIL_SENDER_EMAIL")
        or getattr(settings, "GMAIL_SENDER_EMAIL", None)
        or "noreply@solvenow.app"
    )
    sender_email = str(sender_email).strip().strip("'\"")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email

    html_part = MIMEText(html_content, "html")
    msg.attach(html_part)

    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    body = json.dumps({"raw": raw_message}).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 201, 202):
                logger.info(f"Email successfully sent via Gmail API to {to_email}")
                return True
    except Exception as e:
        logger.error(f"Gmail API message send failed: {e}")

    return False


def _send_email_via_smtp(to_email: str, subject: str, html_content: str) -> bool:
    """
    Fallback: Send email via standard SMTP if configured.
    """
    smtp_host = settings.SMTP_HOST
    smtp_port = settings.SMTP_PORT
    smtp_user = settings.SMTP_USER
    smtp_password = settings.SMTP_PASSWORD
    smtp_from = settings.SMTP_FROM_EMAIL or "noreply@solvenow.app"

    if not (smtp_host and smtp_user and smtp_password):
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, [to_email], msg.as_string())
            logger.info(f"Email sent via SMTP to {to_email}")
            return True
    except Exception as e:
        logger.error(f"SMTP email send failed: {e}")

    return False


def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """
    Send an email using Gmail API (primary) or SMTP (fallback).
    If no credentials are configured, logs a warning and returns False cleanly
    so application routes do not crash.
    """
    if _send_email_via_gmail_api(to_email, subject, html_content):
        return True

    if _send_email_via_smtp(to_email, subject, html_content):
        return True

    logger.warning(
        f"Email sending skipped for {to_email}: No valid Gmail API or SMTP credentials configured."
    )
    return False


def send_verification_otp(to_email: str, otp_code: str) -> bool:
    """
    Send a 6-digit email verification OTP to the specified address.
    """
    subject = f"SolveNow — {otp_code} is your Email Verification Code"
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f5f7; margin: 0; padding: 30px;">
      <div style="max-width: 500px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 30px; border: 1px solid #e2e8f0;">
        <h2 style="color: #0f172a; margin-top: 0;">SolveNow Verification</h2>
        <p style="color: #475569; font-size: 15px;">Welcome to SolveNow! Enter the 6-digit verification code below to verify your email address:</p>
        <div style="background: #f1f5f9; border-radius: 8px; padding: 20px; text-align: center; margin: 25px 0;">
          <span style="font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #2563eb;">{otp_code}</span>
        </div>
        <p style="color: #64748b; font-size: 13px;">This code expires in <strong>10 minutes</strong> and can only be used once.</p>
        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 25px 0;" />
        <p style="color: #94a3b8; font-size: 12px; margin-bottom: 0;">If you did not request this code, please ignore this email.</p>
      </div>
    </body>
    </html>
    """
    return send_email(to_email, subject, html_content)


def send_password_reset_otp(to_email: str, otp_code: str) -> bool:
    """
    Send a 6-digit password reset OTP to the specified address.
    """
    subject = f"SolveNow — {otp_code} is your Password Reset Code"
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f5f7; margin: 0; padding: 30px;">
      <div style="max-width: 500px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 30px; border: 1px solid #e2e8f0;">
        <h2 style="color: #0f172a; margin-top: 0;">Password Reset Request</h2>
        <p style="color: #475569; font-size: 15px;">We received a request to reset your SolveNow password. Use the code below to verify your identity:</p>
        <div style="background: #f1f5f9; border-radius: 8px; padding: 20px; text-align: center; margin: 25px 0;">
          <span style="font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #dc2626;">{otp_code}</span>
        </div>
        <p style="color: #64748b; font-size: 13px;">This code expires in <strong>10 minutes</strong>. Never share this code with anyone.</p>
        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 25px 0;" />
        <p style="color: #94a3b8; font-size: 12px; margin-bottom: 0;">If you did not request a password reset, please secure your account immediately.</p>
      </div>
    </body>
    </html>
    """
    return send_email(to_email, subject, html_content)
