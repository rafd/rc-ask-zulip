"""RC OAuth client and FastAPI dependencies for gating the app.

We use Authlib's Starlette integration for the authorization-code flow against
www.recurse.com, store the user profile and tokens in a signed session cookie,
and transparently refresh access tokens when they expire.
"""

import os
import time

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import HTTPException, Request

RC_AUTHORIZE_URL = "https://www.recurse.com/oauth/authorize"
RC_TOKEN_URL = "https://www.recurse.com/oauth/token"
RC_API_BASE_URL = "https://www.recurse.com/api/v1/"


def _dev_auth_bypass_enabled() -> bool:
    v = os.environ.get("DEV_AUTH_BYPASS", "").strip().lower()
    return v in ("1", "true", "yes")


def _dev_bypass_user() -> dict:
    return {
        "id": 0,
        "name": os.environ.get("DEV_AUTH_BYPASS_NAME", "Dev (no OAuth)"),
        "email": "dev@localhost",
        "image_path": "",
    }


oauth = OAuth()
oauth.register(
    name="recurse",
    client_id=os.environ.get("RC_CLIENT_ID", ""),
    client_secret=os.environ.get("RC_CLIENT_SECRET", ""),
    authorize_url=RC_AUTHORIZE_URL,
    access_token_url=RC_TOKEN_URL,
    api_base_url=RC_API_BASE_URL,
)


def _now() -> float:
    """Indirection so tests can monkeypatch the clock."""
    return time.time()


def current_user(request: Request) -> dict | None:
    """Return the user dict stored in the session, or None."""
    if _dev_auth_bypass_enabled():
        return _dev_bypass_user()
    return request.session.get("user")


async def get_valid_token(request: Request) -> dict:
    """Return a non-expired token dict, refreshing if needed.

    Raises HTTPException(401) and clears the session if no token is present
    or the refresh fails.
    """
    token = request.session.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    expires_at = token.get("expires_at", 0)
    if expires_at - _now() > 60:
        return token

    refresh_token = token.get("refresh_token")
    if not refresh_token:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Session expired")

    try:
        new_token = await oauth.recurse.fetch_access_token(
            grant_type="refresh_token",
            refresh_token=refresh_token,
        )
    except OAuthError:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Session expired")

    if "expires_at" not in new_token and "expires_in" in new_token:
        new_token["expires_at"] = int(_now()) + int(new_token["expires_in"])
    request.session["token"] = dict(new_token)
    return request.session["token"]


async def require_user(request: Request) -> dict:
    """FastAPI dependency: require a logged-in user with a valid token."""
    if _dev_auth_bypass_enabled():
        return _dev_bypass_user()
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    await get_valid_token(request)
    return user
