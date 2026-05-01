"""Tests for RC OAuth login gating.

Mocks RC OAuth/token/profile endpoints with respx and drives the FastAPI app
with TestClient. The session cookie is signed by SessionMiddleware, so we don't
inspect its contents directly — we drive the flow through real endpoints and
assert observable behavior.
"""

import os
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

# Set required env vars before importing the app.
os.environ.setdefault("RC_CLIENT_ID", "test-client-id")
os.environ.setdefault("RC_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("RC_REDIRECT_URI", "http://testserver/auth/callback")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-do-not-use-in-prod")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


@pytest.fixture
def client():
    return TestClient(main.app, follow_redirects=False)


@pytest.fixture
def authed_client(client):
    """A TestClient that has already completed the OAuth flow."""
    with respx.mock(assert_all_called=False) as mock:
        mock.post("https://www.recurse.com/oauth/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "test-access-token",
                    "refresh_token": "test-refresh-token",
                    "token_type": "Bearer",
                    "expires_in": 7200,
                },
            )
        )
        mock.get("https://www.recurse.com/api/v1/people/me").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 42,
                    "name": "Test Recurser",
                    "email": "test@recurse.com",
                    "image_path": "/assets/people/test.jpg",
                },
            )
        )
        login_resp = client.get("/login")
        assert login_resp.status_code in (302, 307)
        state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]
        cb_resp = client.get(f"/auth/callback?code=fake-code&state={state}")
        assert cb_resp.status_code in (302, 307)
    return client


def test_landing_page_shown_when_unauthenticated(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Login with Recurse Center" in resp.text


def test_protected_json_route_returns_401_when_unauthenticated(client):
    resp = client.get("/ask?q=hi")
    assert resp.status_code == 401


def test_login_redirects_to_recurse(client):
    resp = client.get("/login")
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    parsed = urlparse(location)
    assert parsed.netloc == "www.recurse.com"
    assert parsed.path == "/oauth/authorize"
    qs = parse_qs(parsed.query)
    assert qs["client_id"] == ["test-client-id"]
    assert qs["redirect_uri"] == ["http://testserver/auth/callback"]
    assert qs["response_type"] == ["code"]
    assert "state" in qs


@respx.mock
def test_callback_exchanges_code_and_creates_session(client):
    respx.post("https://www.recurse.com/oauth/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "test-access-token",
                "refresh_token": "test-refresh-token",
                "token_type": "Bearer",
                "expires_in": 7200,
            },
        )
    )
    respx.get("https://www.recurse.com/api/v1/people/me").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 42,
                "name": "Test Recurser",
                "email": "test@recurse.com",
                "image_path": "/assets/people/test.jpg",
            },
        )
    )

    login_resp = client.get("/login")
    state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]

    cb_resp = client.get(f"/auth/callback?code=fake-code&state={state}")
    assert cb_resp.status_code in (302, 307)
    assert cb_resp.headers["location"] in ("/", "http://testserver/")

    home_resp = client.get("/")
    assert home_resp.status_code == 200
    assert "Login with Recurse Center" not in home_resp.text


def test_authenticated_user_sees_app(authed_client):
    resp = authed_client.get("/")
    assert resp.status_code == 200
    assert "Login with Recurse Center" not in resp.text
    # pair.html has the checkin grid; landing.html does not.
    assert "Pair" in resp.text or "pair" in resp.text


def test_logout_clears_session(authed_client):
    logout_resp = authed_client.get("/logout")
    assert logout_resp.status_code in (302, 307)
    home_resp = authed_client.get("/")
    assert home_resp.status_code == 200
    assert "Login with Recurse Center" in home_resp.text


def test_expired_token_is_refreshed_transparently(authed_client, monkeypatch):
    # Force the stored token to look expired.
    import auth as auth_module

    real_now = time.time

    def fake_now():
        return real_now() + 10_000  # well past 2h expiry

    monkeypatch.setattr(auth_module, "_now", fake_now)

    with respx.mock(assert_all_called=False) as mock:
        refresh_route = mock.post("https://www.recurse.com/oauth/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "new-access-token",
                    "refresh_token": "new-refresh-token",
                    "token_type": "Bearer",
                    "expires_in": 7200,
                },
            )
        )
        resp = authed_client.get("/conversations")
        assert resp.status_code == 200
        assert refresh_route.called


def test_failed_refresh_clears_session_and_returns_401(authed_client, monkeypatch):
    import auth as auth_module

    real_now = time.time
    monkeypatch.setattr(auth_module, "_now", lambda: real_now() + 10_000)

    with respx.mock(assert_all_called=False) as mock:
        mock.post("https://www.recurse.com/oauth/token").mock(
            return_value=httpx.Response(400, json={"error": "invalid_grant"})
        )
        resp = authed_client.get("/conversations")
        assert resp.status_code == 401
        # Session cleared — landing page is shown again.
        home = authed_client.get("/")
        assert "Login with Recurse Center" in home.text
