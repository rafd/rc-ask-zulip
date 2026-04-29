import json
import logging
import os
from collections import deque

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import db
from agent import AgentAnswerError, run_agent

load_dotenv()
logger = logging.getLogger(__name__)

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


@app.get("/ask-stream")
def ask_stream(q: str):
    def _sse(step: str, data: dict) -> str:
        return f"data: {json.dumps({'step': step, 'data': data})}\n\n"

    def event_generator():
        pending_events = deque()

        def progress_callback(step: str, data: dict):
            pending_events.append(_sse(step, data))

        try:
            messages, final_answer = run_agent(q, progress_callback=progress_callback)
            while pending_events:
                yield pending_events.popleft()
            conv_id = db.save_conversation(q, messages, final_answer)
            yield _sse("complete", {"id": conv_id, "messages": messages, "final_answer": final_answer})
        except AgentAnswerError as e:
            while pending_events:
                yield pending_events.popleft()
            yield _sse("error", {"message": e.message})
        except Exception:
            logger.exception("Unexpected error in ask-stream")
            while pending_events:
                yield pending_events.popleft()
            yield _sse("error", {"message": "Unexpected server error while streaming response."})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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
