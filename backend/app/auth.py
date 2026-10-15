"""
auth.py — accounts and sessions: password hashing, the signed session cookie, and the
`current_user` dependency that every protected route uses.

Who uses it: routes/auth.py (signup/login/logout) and every route that needs a logged-in user.
Depends on: argon2-cffi (password hashing), itsdangerous (signing the cookie), db.

How a session works, in plain words:
1. On login we create a small token containing the user's id and sign it with SECRET_KEY.
2. The browser stores it in an HttpOnly cookie (JavaScript can't read it, so XSS can't steal it).
3. On every request we verify the signature. If anyone edits the cookie, the signature no longer
   matches and we treat them as logged out. No session table is needed.
"""
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import db
from .config import settings
from .errors import ApiError

COOKIE_NAME = "cw_session"
SESSION_MAX_AGE = 30 * 24 * 3600  # 30 days

# Argon2id is the current recommended password hash: deliberately slow and memory-hungry, so an attacker
# who steals the database can't try billions of guesses per second.
_hasher = PasswordHasher()
_serializer = URLSafeTimedSerializer(settings.secret_key, salt="cw-session")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def set_session_cookie(response: Response, user_id: int) -> None:
    """Sign the user id and put it in the HttpOnly session cookie."""
    token = _serializer.dumps({"uid": user_id})
    # SameSite=Lax blocks the cookie on cross-site POSTs (first CSRF defence; the Origin check is the second).
    # Split hosting (frontend on another domain) needs SameSite=None, which browsers only allow with Secure.
    same_site = "none" if settings.cors_origin_list and settings.is_https else "lax"
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_MAX_AGE, httponly=True,
        secure=settings.is_https, samesite=same_site, path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def user_id_from_request(request: Request) -> int | None:
    """Read and verify the session cookie. Returns the user id or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid") if isinstance(data, dict) else None
    return int(uid) if isinstance(uid, int) else None


async def current_user(request: Request) -> dict:
    """FastAPI dependency: the logged-in user's row, or a 401 error.

    Use it as `user: dict = Depends(current_user)` in any route that needs login.
    """
    uid = user_id_from_request(request)
    if uid is None:
        raise ApiError(401, "not_logged_in", "Please log in to continue.")
    user = await db.fetch_one("SELECT * FROM users WHERE id = ?", (uid,))
    if user is None:
        raise ApiError(401, "not_logged_in", "Please log in to continue.")
    return user


async def admin_user(request: Request) -> dict:
    """Dependency for /system: the first user (or ADMIN_EMAIL) is the admin."""
    user = await current_user(request)
    if not user["is_admin"]:
        raise ApiError(403, "admin_only", "Only the administrator can see the system view.")
    return user


def user_out(user: dict) -> dict:
    """The public shape of a user (never includes the password hash or alert secrets)."""
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"] or user["email"].split("@")[0],
        "timezone": user["timezone"],
        "is_admin": bool(user["is_admin"]),
    }
