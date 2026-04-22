# Ask RC Zulip

A small web app for [Recurse Center](https://www.recurse.com/) participants: ask what RCers think about a topic, search public Zulip conversations, and get an AI summary with citations.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Python 3.12+ (see `.python-version`)
- [Ollama](https://ollama.com/) running locally (default), **or** any other **OpenAI-compatible** HTTP API (set `OPENAI_BASE_URL` / `OPENAI_API_KEY`)
- A Zulip API key with access to the RC organization’s public streams

### Ollama (default local LLM)

- **macOS (Homebrew):** from the repo root, run `brew bundle` (see [`Brewfile`](Brewfile)), or install from [ollama.com/download](https://ollama.com/download).
- **Optional (manual):** [`docker-compose.yml`](docker-compose.yml) can run Ollama in Docker if you set that up yourself; **`run.sh` does not use Docker**.
- **Open WebUI (optional):** a browser UI for chatting with the same local Ollama models—installed on the fly with **`uv`** (no Docker). With Ollama on **11434** (same as **`./run.sh run`**), run:

  ```bash
  ./run.sh webui
  ```

  Then open [http://127.0.0.1:8080](http://127.0.0.1:8080) (default for the pip-installed server). See [Open WebUI](https://github.com/open-webui/open-webui) for env vars (for example `OLLAMA_BASE_URL`) if your Ollama URL is non-default.
- **`./run.sh run`** tries to start Ollama if nothing answers on port **11434**: it runs `ollama serve` in the background (if the CLI is installed) or on macOS tries `open -a Ollama`. If this script started `ollama serve`, **stopping the dev server** (Ctrl+C or exit) **stops that `ollama serve` process**. If only the macOS app was used, the app keeps running. Logs from script-started `ollama serve` go to `.ollama-serve.log` (gitignored). Set **`OLLAMA_AUTOSTART=0`** to require Ollama already running instead.
- Pull a model that matches `OPENAI_MODEL` (default `llama3.1`), for example:

  ```bash
  ./run.sh pull-model
  ```

  or: `ollama pull llama3.1`

## Setup

1. Clone the repo and enter the directory.

2. Create a `.env` file in the project root:

   ```env
   ZULIP_SITE=your-org.zulipchat.com
   ZULIP_EMAIL=your-bot-or-account@example.com
   ZULIP_API_KEY=...
   ```

   Optional LLM overrides (defaults work with local Ollama):

   ```env
   OPENAI_BASE_URL=http://127.0.0.1:11434/v1
   OPENAI_API_KEY=ollama
   OPENAI_MODEL=llama3.1
   ```

   For a remote OpenAI-compatible endpoint, set `OPENAI_BASE_URL` and a real `OPENAI_API_KEY`, and use `SKIP_OLLAMA_CHECK=1 ./run.sh run` if the server is not on localhost:11434.

   To disable auto-start and require Ollama already listening locally: `OLLAMA_AUTOSTART=0`.

3. Install Python dependencies (includes dev tools such as pytest):

   ```bash
   ./run.sh setup
   ```

   On macOS you can also install Ollama via Homebrew in the same step:

   ```bash
   ./run.sh setup --brew
   ```

   Or: `uv sync --extra dev`

## Run

```bash
./run.sh run
```

Or: `uv run python main.py` (bypasses `run.sh`; you must start Ollama yourself). With `./run.sh run`, use `SKIP_OLLAMA_CHECK=1` to skip the local Ollama check and auto-start (e.g. remote `OPENAI_BASE_URL`).

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) (default uvicorn port). Submit a question on the home page; the app searches Zulip, calls the configured LLM, and shows the answer with linked message excerpts.

## Tests

```bash
uv run pytest
```

## How it works (briefly)

- **Backend:** [FastAPI](https://fastapi.tiangolo.com/) (`main.py`) serves static pages and JSON APIs.
- **Search:** `zulip_search.py` calls Zulip’s message API with a public-channels narrow and full-text search; results are deduplicated across queries.
- **Privacy:** `anonymize.py` strips sender identity from what the model sees and normalizes mentions (see code for check-in stream handling).
- **Agent:** `agent.py` uses the OpenAI Python SDK against an OpenAI-compatible API (default: Ollama at `http://127.0.0.1:11434/v1`). Tool calling and strict JSON-schema responses are optional and model-dependent.
- **Storage:** Conversations are stored in SQLite (`conversations.db`) via `db.py`.

## API (for debugging or integrations)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Home (search + past conversations) |
| GET | `/conversation` | Result page (`?q=...` or `?id=...`) |
| GET | `/ask?q=...` | Run agent; returns `id`, `messages`, `final_answer` |
| GET | `/conversations` | List recent saved conversations |
| GET | `/conversation-data/{id}` | Load one conversation |

## Project layout

| Path | Role |
|------|------|
| `main.py` | App entry, routes |
| `agent.py` | LLM agent + tool wiring |
| `zulip_search.py` | Zulip client + search |
| `anonymize.py` | Message redaction for the model |
| `db.py` | SQLite persistence |
| `static/` | HTML UI |
| `run.sh` | Local setup / Ollama preflight / dev server |
| `Brewfile` | macOS Homebrew deps (Ollama) |
| `docker-compose.yml` | Optional Ollama container |
| `NOTES.md` | Product notes and future ideas |

See [`STUDY_GUIDE.md`](STUDY_GUIDE.md) for a deeper walkthrough of architecture and tradeoffs.
