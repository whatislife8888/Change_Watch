"""
routes/auth.py — signup, login, logout and "who am I".

Who uses it: the Login and Signup pages, and the frontend's startup check (`GET /api/auth/me`).
Depends on: auth.py (hashing + cookie), security.py (rate limits), db.
"""
import re

from fastapi import APIRouter, Depends, Request, Response

from .. import db
from ..auth import (clear_session_cookie, current_user, hash_password, set_session_cookie, user_out,
                    verify_password)
from ..config import settings
from ..errors import ApiError
from ..schemas import LoginIn, SignupIn, UserOut
from ..security import client_ip, login_limiter, signup_limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("/signup", response_model=UserOut)
async def signup(body: SignupIn, request: Request, response: Response) -> dict:
    """Create an account and log the new user in. The first account (or ADMIN_EMAIL) becomes admin."""
    wait = signup_limiter.hit(client_ip(request))
    if wait:
        raise ApiError(429, "too_many_signups", "Too many sign-ups from this network. Try again later.")
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ApiError(422, "invalid_email", "Enter a valid email address.")
    if await db.fetch_one("SELECT id FROM users WHERE email = ?", (email,)):
        raise ApiError(409, "email_taken", "An account with this email already exists. Try logging in.")

    user_count = await db.fetch_value("SELECT COUNT(*) FROM users")
    is_admin = user_count == 0 or (settings.admin_email and email == settings.admin_email.lower())
    user_id = await db.execute(
        "INSERT INTO users (email, password_hash, display_name, is_admin, created_at) VALUES (?, ?, ?, ?, ?)",
        (email, hash_password(body.password), body.display_name.strip(), 1 if is_admin else 0, db.now_iso()),
    )
    set_session_cookie(response, user_id)
    user = await db.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
    return user_out(user)


@router.post("/login", response_model=UserOut)
async def login(body: LoginIn, request: Request, response: Response) -> dict:
    """Check the password and set the session cookie. Limited to 10 attempts per minute per IP."""
    wait = login_limiter.hit(client_ip(request))
    if wait:
        raise ApiError(429, "too_many_attempts", f"Too many attempts. Try again in {int(wait)} seconds.",
                       headers={"Retry-After": str(int(wait))})
    user = await db.fetch_one("SELECT * FROM users WHERE email = ?", (body.email.strip().lower(),))
    # Same message whether the email or the password is wrong, so attackers can't discover accounts.
    if not user or not verify_password(user["password_hash"], body.password):
        raise ApiError(401, "bad_credentials", "That email and password don't match.")
    set_session_cookie(response, user["id"])
    return user_out(user)


@router.post("/logout")
async def logout(response: Response) -> dict:
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(current_user)) -> dict:
    return user_out(user)
