import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from zulip_search import search_messages

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    with open("static/index.html") as f:
        return f.read()


@app.get("/search")
def search(q: str):
    return search_messages(q)


if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
