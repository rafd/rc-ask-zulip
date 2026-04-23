import logging
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import db
from agent import AgentAnswerError, run_agent
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
app.mount("/static", StaticFiles(directory="static"), name="static")

db.init_db()

# Used to get the zulip site for the permalinks to the Zulip messages
@app.get("/config")
def config():
    return {"zulip_site": os.environ.get("ZULIP_SITE", "")}


@app.get("/", response_class=HTMLResponse)
def index():
    with open("static/index.html") as f:
        return f.read()


@app.get("/conversation", response_class=HTMLResponse)
def conversation():
    with open("static/conversation.html") as f:
        return f.read()


@app.get("/ask")
def ask(q: str):
    try:
        messages, final_answer = run_agent(q)
    except AgentAnswerError as e:
        raise HTTPException(status_code=422, detail=e.message) from e
    conv_id = db.save_conversation(q, messages, final_answer)
    return {"id": conv_id, "messages": messages, "final_answer": final_answer}


@app.get("/pair", response_class=HTMLResponse)
def pair():
    with open("static/pair.html") as f:
        return f.read()


@app.get("/api/checkin-pair")
def checkin_pair():
    zulip_site = os.environ.get("ZULIP_SITE", "")
    return build_grouped(zulip_site)


@app.get("/conversations")
def conversations():
    return db.list_conversations()


@app.get("/conversation-data/{conv_id}")
def conversation_data(conv_id: int):
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
