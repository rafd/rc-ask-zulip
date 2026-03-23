import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from agent import run_agent

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


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
    return {"messages": messages, "final_answer": final_answer}


if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
