# Ask RC Zulip

A small web app for [Recurse Center](https://www.recurse.com/) participants: ask what RCers think about a topic, search public Zulip conversations, and get an AI summary with citations.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Python 3.12+ (see `.python-version`)
- [Ollama](https://ollama.com/) running locally (default), **or** any other **OpenAI-compatible** HTTP API (set `OPENAI_BASE_URL` / `OPENAI_API_KEY`)
- A Zulip API key with access to the RC organization’s public streams

### Ollama (default local LLM)

- **macOS (Homebrew):** `./install.sh --brew` runs `brew bundle` (see [`Brewfile`](Brewfile)). Use **`./setup_ollama.sh`** if you only want that step (it requires Homebrew and runs `brew bundle`). Or install Ollama from [ollama.com/download](https://ollama.com/download).
- **Optional (manual):** [`docker-compose.yml`](docker-compose.yml) can run Ollama in Docker if you set that up yourself; the shell scripts do not start Docker.
- **Open WebUI (optional):** browser UI for the same local Ollama models. After `./install.sh`, run:

  ```bash
  ./Ollama.sh
  ```

  Then open [http://127.0.0.1:8080](http://127.0.0.1:8080) (default for the PyPI server). See [Open WebUI](https://github.com/open-webui/open-webui) for env vars (for example `OLLAMA_BASE_URL`) if Ollama is not on the default URL.

  If this script started `ollama serve` in the background, exiting Open WebUI (Ctrl+C) stops that process. If you used the macOS Ollama app (`open -a Ollama`), the app keeps running. Background `ollama serve` logs append to `.ollama-serve.log` (gitignored).

- Pull a model that matches `OPENAI_MODEL` (default `llama3.1`): `ollama pull llama3.1`

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

   For a remote OpenAI-compatible endpoint, set `OPENAI_BASE_URL` and a real `OPENAI_API_KEY`. Start Ollama (or your API) yourself before using the app when the URL points at localhost.

3. Install Python dependencies:

   ```bash
   ./install.sh
   ```

   On macOS you can also install Ollama via Homebrew in the same step:

   ```bash
   ./install.sh --brew
   ```

   Or: `uv sync`

## Run

```bash
./run.sh
```

Skip the Ollama bootstrap when the LLM is not local (or Ollama is already running and you want to avoid the check):

```bash
./run.sh --no-ollama
```

Or: `uv run python main.py` (expects a working environment and `.env` loaded by the app via `python-dotenv`). With `./run.sh`, `.env` is sourced by the shell before Python starts.

**`./run.sh`** runs **`./Ollama.sh --ollama-only`** first (ensures **:11434**; may start a detached **`ollama serve`** — see **`./Ollama.sh --help`**), then **`./install.sh`** if **`.venv`** is missing, then the app. For Ollama **and** Open WebUI in one terminal, use **`./Ollama.sh`** alone (~**8080**).

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) (default uvicorn port). Submit a question on the home page; the app searches Zulip, calls the configured LLM, and shows the answer with linked message excerpts.

## How it works (briefly)

- **Backend:** [FastAPI](https://fastapi.tiangolo.com/) (`main.py`) serves static pages and JSON APIs.
- **Search:** `zulip_search.py` calls Zulip’s message API with a public-channels narrow and full-text search; results are deduplicated across queries.
- **Agent:** `agent.py` bootstraps with a real Zulip search, then runs an OpenAI-compatible chat loop (default: Ollama at `http://127.0.0.1:11434/v1`). The model must return a fixed JSON shape (`section_1`–`section_3` with short citation quotes). Message payloads include sender and stream fields as returned by Zulip (local use; treat credentials and data accordingly).
- **Legacy:** `anonymize.py` is unused in the pipeline; it remains in the repo for reference only.
- **Storage:** Conversations are stored in SQLite (`conversations.db`) via `db.py`.

## API (for debugging or integrations)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Home (search + past conversations) |
| GET | `/conversation` | Result page (`?q=...` or `?id=...`) |
| GET | `/config` | Public Zulip site hostname for permalinks (`zulip_site`) |
| GET | `/ask?q=...` | Run agent; returns `id`, `messages`, `final_answer` |
| GET | `/conversations` | List recent saved conversations |
| GET | `/conversation-data/{id}` | Load one conversation |

## Project layout

| Path | Role |
|------|------|
| `main.py` | App entry, routes |
| `agent.py` | LLM agent + tool wiring |
| `zulip_search.py` | Zulip client + search |
| `anonymize.py` | Unused (historical redaction helpers) |
| `db.py` | SQLite persistence |
| `static/` | HTML UI |
| `install.sh` | `uv sync`; optional `--brew` |
| `run.sh` | `Ollama.sh --ollama-only` unless `--no-ollama`; then `install.sh` if needed; app **:8000** |
| `Ollama.sh` | Ollama on **:11434**; add **`--ollama-only`** to skip WebUI; default also starts Open WebUI **:8080** |
| `setup_ollama.sh` | Require Homebrew; `brew bundle` from `Brewfile` |
| `Brewfile` | macOS Homebrew deps (Ollama) |
| `docker-compose.yml` | Optional Ollama container |
| `NOTES.md` | Product notes and future ideas |

See [`STUDY_GUIDE.md`](STUDY_GUIDE.md) for a deeper walkthrough of architecture and tradeoffs.
