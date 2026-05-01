import logging
import os

import httpx
import uvicorn
from authlib.integrations.starlette_client import OAuthError
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import db
from agent import AgentAnswerError, run_agent
from auth import current_user, oauth, require_user
from checkin_fetch import build_grouped

load_dotenv()

_log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
_log_level = getattr(logging, _log_level_name, None)
if not isinstance(_log_level, int):
    _log_level_name = "INFO"
    _log_level = logging.INFO
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)

app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "dev-only-change-me"),
    same_site="lax",
    https_only=os.environ.get("SESSION_COOKIE_SECURE", "").lower() == "true",
)
app.mount("/static", StaticFiles(directory="static"), name="static")

db.init_db()


def _render_page(filename: str, user: dict | None) -> str:
    with open(f"static/{filename}") as f:
        html = f.read()
    name = (user or {}).get("name", "")
    return html.replace("{{user_name}}", name)


def _serve_app_or_landing(request: Request, app_page: str) -> HTMLResponse:
    user = current_user(request)
    if user is None:
        return HTMLResponse(_render_page("landing.html", None))
    return HTMLResponse(_render_page(app_page, user))


@app.get("/config")
def config():
    return {"zulip_site": os.environ.get("ZULIP_SITE", "")}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return _serve_app_or_landing(request, "pair.html")


@app.get("/zulip", response_class=HTMLResponse)
def zulip_ask_page(request: Request):
    return _serve_app_or_landing(request, "zulip.html")


@app.get("/conversation", response_class=HTMLResponse)
def conversation(request: Request):
    return _serve_app_or_landing(request, "conversation.html")


@app.get("/pair", response_class=HTMLResponse)
def pair(request: Request):
    return _serve_app_or_landing(request, "pair.html")


@app.get("/login")
async def login(request: Request):
    redirect_uri = os.environ.get("RC_REDIRECT_URI") or str(
        request.url_for("auth_callback")
    )
    return await oauth.recurse.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.recurse.authorize_access_token(request)
    except OAuthError:
        raise HTTPException(status_code=400, detail="OAuth callback failed")

    async with httpx.AsyncClient() as http:
        me_resp = await http.get(
            "https://www.recurse.com/api/v1/people/me",
            headers={"Authorization": f"Bearer {token['access_token']}"},
        )
    if me_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch RC profile")

    me = me_resp.json()
    request.session["token"] = dict(token)
    request.session["user"] = {
        "id": me.get("id"),
        "name": me.get("name", ""),
        "email": me.get("email", ""),
        "image_path": me.get("image_path", ""),
    }
    return RedirectResponse(url="/", status_code=302)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)


@app.get("/ask")
def ask(q: str, user: dict = Depends(require_user)):
    try:
        messages, final_answer = run_agent(q)
    except AgentAnswerError as e:
        raise HTTPException(status_code=422, detail=e.message) from e
    conv_id = db.save_conversation(q, messages, final_answer)
    return {"id": conv_id, "messages": messages, "final_answer": final_answer}


@app.get("/api/checkin-pair")
def checkin_pair(user: dict = Depends(require_user)):
    zulip_site = os.environ.get("ZULIP_SITE", "")
    return build_grouped(zulip_site)


@app.get("/conversations")
def conversations(user: dict = Depends(require_user)):
    return db.list_conversations()


@app.get("/conversation-data/{conv_id}")
def conversation_data(conv_id: int, user: dict = Depends(require_user)):
    row = db.get_conversation(conv_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return row


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        reload=True,
        log_level=_log_level_name.lower(),
    )
