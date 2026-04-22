# Study guide: Ask RC Zulip

## What we're building

- RC members ask a question in the app.
- The app searches **public Zulip**, calls an **LLM** (default: local Ollama), and returns a **summary with citations** (message ids you can open in Zulip).

## How it works (high level)

1. Web UI hits **`main.py`** (FastAPI, `/ask`).
2. **`agent.py`** calls an OpenAI-compatible API (`OPENAI_BASE_URL`, default `http://127.0.0.1:11434/v1`).
3. **`zulip_search.py`** runs when the agent uses search tools.
4. Optionally **`anonymize.py`** (privacy) and **`db.py`** (SQLite history).

## Key decisions and why

- **`openai` client + `OPENAI_BASE_URL`:** one code path for Ollama or cloud.
- **Ollama** is a system install (Brew, etc.), not `pip`—daemon + model weights.
- **`Ollama.sh`:** keep Ollama on **11434**; **`--ollama-only`** exits after that (detached **`ollama serve`** if needed). Default mode then runs Open WebUI via `uv run --with open-webui --with greenlet` and **`DATA_DIR`** (default `~/.open-webui`, ~**8080**).
- **`greenlet`** is in **`pyproject.toml`** so `uv sync` installs it; **`--with greenlet`** matches the usual workaround when SQLAlchemy errors with “No module named 'greenlet'”.
- **Local defaults** (dummy key, local URL) = develop without paid APIs.
- **Cons:** tool/JSON behavior depends on the server; for localhost Ollama, something must serve **:11434** (**`./Ollama.sh`**, desktop app, or **`ollama serve`**).

## How each piece works

- **`main.py`** — Routes, static files, save chats.
- **`agent.py`** — Chat loop, tools.
- **`zulip_search.py`** — `ZULIP_*` env, search public streams.
- **`anonymize.py` / `db.py`** — Redaction; SQLite.
- **`install.sh`** — `uv sync`, optional `--brew`.
- **`run.sh`** — **`./Ollama.sh --ollama-only`** unless **`--no-ollama`**; **`install.sh`** if **`.venv`** is missing; loads **`.env`**; **`exec`** **`main.py`** on **:8000**.
- **`Ollama.sh`** — if **`ollama`** is not on **`PATH`**, runs **`setup_ollama.sh`** (when present). Then **`--ollama-only`** or full (Open WebUI). **`setup_ollama.sh`** — require Homebrew, then **`brew bundle`** (same **`Brewfile`** as **`install.sh --brew`**).

## Things that don't work well

- Small local models are weaker at tools/JSON than big cloud APIs.
- Zulip recall depends on search quality and your query.
- `OPENAI_BASE_URL` on localhost with Ollama down → failed requests until **`./Ollama.sh`**, the desktop app, or **`ollama serve`** is running.
- Zulip credentials are real secrets.

## Key metrics and results

- No fixed benchmark in the repo.
- **Latency** and **quality** depend on hardware, `OPENAI_MODEL`, and how much Zulip context you pass in.
