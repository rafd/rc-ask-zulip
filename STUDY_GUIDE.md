# Study guide: Ask RC Zulip

## What we're building

- RC members ask a question in the app.
- The app searches **public Zulip**, calls an **LLM** (default: local Ollama), and returns a **structured summary** with **three sections** and **short inline quotes** linked to Zulip messages.

## How it works (high level)

1. Web UI hits **`main.py`** (FastAPI, `/ask`).
2. **`agent.py`** runs **`messages_for_agent(question)`** once immediately (real Zulip HTTP), injects that as the first tool round in the chat log, then loops: more optional searches via tools, then a **JSON answer** with **`section_1`–`section_3`**.
3. **`zulip_search.py`** implements search and shapes each message for the model (including **sender** and **stream_id** when present). There is **no anonymization** in the pipeline (local/trusted use).
4. **`db.py`** stores SQLite history.

## Key decisions and why

- **`openai` client + `OPENAI_BASE_URL`:** one code path for Ollama or cloud.
- **Ollama** is a system install (Brew, etc.), not `pip`—daemon + model weights.
- **`Ollama.sh`:** keep Ollama on **11434**; **`--ollama-only`** exits after that (detached **`ollama serve`** if needed). Default mode then runs Open WebUI via `uv run --with open-webui --with greenlet` and **`DATA_DIR`** (default `~/.open-webui`, ~**8080**).
- **`greenlet`** is in **`pyproject.toml`** so `uv sync` installs it; **`--with greenlet`** matches the usual workaround when SQLAlchemy errors with “No module named 'greenlet'”.
- **Local defaults** (dummy key, local URL) = develop without paid APIs.
- **Bootstrap search** guarantees at least one Zulip fetch before the model loop, so every run has tool-grounded context.
- **Strict three-part JSON** keeps the UI simple and avoids unstructured blobs.
- **Tool turns omit `response_format`** when possible so local servers are less likely to break tool calling; a **repair** completion uses **`response_format`** if the first final reply is not valid JSON.
- **Server-Sent Events (SSE) for progress streaming:** `/ask-stream` endpoint uses SSE (text/event-stream) instead of WebSocket because: (1) it's one-way (server → client), (2) HTTP-based and simpler to debug, (3) no external dependencies on the frontend. Progress events are sent as JSON-formatted SSE data events with `step` and `data` fields. The backend calls a `progress_callback` at key points (bootstrap search, each agent turn, tool searches) so users see live updates instead of a blank “Thinking...” state.
- **Cons:** tool/JSON behavior depends on the server; for localhost Ollama, something must serve **:11434** (**`./Ollama.sh`**, desktop app, or **`ollama serve`**).

## How each piece works

- **`main.py`** — Routes, static files, `/config` (Zulip site for links), save chats. **`/ask`** returns full result at once (blocking); **`/ask-stream`** returns SSE stream of progress events plus final answer.
- **`agent.py`** — Bootstrap tool round, chat loop, validates JSON; repair pass on failure. **`run_agent()`** accepts optional `progress_callback(step, data)` function to emit live progress updates at each major step.
- **`zulip_search.py`** — `ZULIP_*` env, search public streams, `prepare_for_agent`.
- **`anonymize.py`** — Not used by the app (legacy).
- **`db.py`** — SQLite persistence.
- **`install.sh`** — `uv sync`, optional `--brew`.
- **`run.sh`** — **`install.sh`** if **`.venv`** is missing; loads **`.env`**; **`curl`** **`${OLLAMA_HOST:-http://127.0.0.1:11434}/api/tags`** and runs **`./Ollama.sh --ollama-only`** if that fails; **`exec`** **`main.py`** on **:8000**.
- **`Ollama.sh`** — if **`ollama`** is not on **`PATH`**, runs **`setup_ollama.sh`** (when present). Then **`--ollama-only`** or full (Open WebUI). **`setup_ollama.sh`** — require Homebrew, then **`brew bundle`** (same **`Brewfile`** as **`install.sh --brew`**).

## Things that don't work well

- Small local models are weaker at tools/JSON than big cloud APIs.
- Zulip recall depends on search quality and your query.
- `OPENAI_BASE_URL` on localhost with Ollama down → failed requests until **`./Ollama.sh`**, the desktop app, or **`ollama serve`** is running.
- Zulip credentials are real secrets; the model sees real names and message text.

## Key metrics and results

- No fixed benchmark in the repo.
- **Latency** and **quality** depend on hardware, `OPENAI_MODEL`, and how much Zulip context you pass in.
