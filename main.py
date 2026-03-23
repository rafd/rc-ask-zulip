import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import db
from agent import run_agent

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

db.init_db()


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
    messages, final_answer = run_agent(q)
    conv_id = db.save_conversation(q, messages, final_answer)
    return {"id": conv_id, "messages": messages, "final_answer": final_answer}


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
    uvicorn.run("main:app", reload=True)
