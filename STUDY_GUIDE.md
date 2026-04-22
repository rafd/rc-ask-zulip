# Study guide: Ask RC Zulip

This file explains the project for someone who has never seen the codebase. After reading it, you should be able to describe the app in an interview.

## What we're building

**Ask RC Zulip** is a small web app for Recurse Center participants. You type a question (for example, “What do people think about pair programming?”). The app searches **public Zulip** threads at RC, sends context to a **language model**, and returns a **summary** with **citations** (Zulip message ids you can open in the UI).

**Who it's for:** RC community members who want a quick sense of what was discussed on Zulip without reading every thread.

## How it works (high level)

1. The user opens the site and submits a question.
2. The **FastAPI** backend (`main.py`) receives the question (for example via `/ask`).
3. **`agent.py`** builds a chat request to an **OpenAI-compatible** HTTP API. By default that API is **Ollama** on your machine (`http://127.0.0.1:11434/v1`).
4. **`zulip_search.py`** can search Zulip when the agent uses tools (tool calling is optional and may be commented out depending on the model).
5. Messages shown to the model can be **anonymized** in `anonymize.py` so sender names are not leaked to the LLM.
6. The final text (and full message log) can be stored in **SQLite** via `db.py` for later viewing.

## Key decisions and why

### OpenAI-compatible client + env-based URL (default Ollama)

- **What was chosen:** The official **`openai`** Python package talks to any server that implements the same HTTP shape as OpenAI’s Chat Completions API. We point it at Ollama’s `/v1` endpoint by default using **`OPENAI_BASE_URL`**.
- **Alternatives:** (1) The PyPI package named **`ollama`** — a different client API. (2) Calling **OpenAI’s cloud** only. (3) A custom HTTP client for each provider.
- **Why this choice:** One code path works for **local Ollama** and for other **proxies or hosts** that speak the same protocol. You only change environment variables.
- **Tradeoffs:** Not every model supports **tools** or **strict JSON schema** the same way; behavior depends on what sits behind the URL.
- **Analogy:** It is like using a single USB-C charger: the “socket” is OpenAI-compatible HTTP; Ollama is one device that fits that socket.

### Ollama is not a `pip` dependency

- **What was chosen:** Ollama is installed as a **system app** (or via **Homebrew** / **Docker**). The repo lists that in **`Brewfile`** and **`docker-compose.yml`**, not in `pyproject.toml`.
- **Alternatives:** Add the **`ollama`** PyPI package — but that is only a **Python client**, not the **server** that listens on port 11434.
- **Why:** `pip install` cannot install or start the Ollama daemon or download multi-gigabyte models. Treating Ollama as a **runtime dependency** (like Postgres) matches how it actually runs.
- **Tradeoffs:** Setup is two steps: install Ollama, then `ollama pull` a model. **`run.sh run`** can start **`ollama serve`** for you and tears it down when the dev server exits (PID + shell trap), unless Ollama was already up or only the macOS app was launched (`open -a Ollama`), in which case nothing is killed by the script.

### Local-first defaults

- **Defaults:** `OPENAI_BASE_URL=http://127.0.0.1:11434/v1`, `OPENAI_API_KEY=ollama` (Ollama does not require a real secret), `OPENAI_MODEL=llama3.1`.
- **Why:** Developers can run entirely **offline** from paid cloud LLMs if they have Ollama and a pulled model.

## How each piece works

### `main.py`

- **One sentence:** Defines the FastAPI app, static files, and routes that load HTML and JSON for questions and saved conversations.
- **How:** `GET /ask` calls `run_agent` from `agent.py` and saves the result with `db.save_conversation`. Other routes serve pages or list past chats.
- **Example:** `GET /ask?q=rust` → JSON with `final_answer` and `messages`.

### `agent.py`

- **One sentence:** Runs a loop that calls the LLM with a system prompt and user question until the model returns a final text answer (and optionally handles tool calls).
- **How:** `_openai_client()` reads **`OPENAI_BASE_URL`**, **`OPENAI_API_KEY`**, and `_chat_model()` reads **`OPENAI_MODEL`**. It uses `client.chat.completions.create(...)`. Tool schemas and JSON response formats may be enabled when the backend model supports them.
- **Example:** Input question string → output `(list of chat messages, final_answer string)`.

### `zulip_search.py`

- **One sentence:** Talks to Zulip’s REST API to search **public** channels and returns normalized message payloads for the agent.
- **How:** Builds a narrow (public channels + search operator), calls `messages`, then prepares dicts (id, timestamp, content, etc.). Uses env vars **`ZULIP_SITE`**, **`ZULIP_EMAIL`**, **`ZULIP_API_KEY`**.
- **Example:** Query `"pair programming"` → list of message dicts (then possibly anonymized).

### `anonymize.py`

- **One sentence:** Redacts or normalizes message content before the LLM sees it (for example sender identity).
- **How:** String transforms on HTML/plain content per project rules (see code and comments).
- **Example:** A message with a full name → content safe to send to the model under your privacy policy.

### `db.py`

- **One sentence:** Persists conversations in SQLite so the UI can reload past Q&A.
- **How:** Typical CRUD-style helpers: init schema, save rows, list and get by id.
- **Example:** After `/ask`, a new row with question, serialized messages, and answer.

### `run.sh`

- **One sentence:** Installs Python deps, optionally runs Homebrew bundle for Ollama, can pull a model, and starts the dev server after ensuring local Ollama is up (starting it if needed).
- **How:** `setup` runs `uv sync --extra dev`. For `run`, if the preflight applies (`OPENAI_BASE_URL` points at local `:11434` and `SKIP_OLLAMA_CHECK` is not set), the script waits for `http://127.0.0.1:11434/api/tags`. If down and `OLLAMA_AUTOSTART` is not `0`, it runs `ollama serve` in the background, registers a **`trap`** to **`kill` that PID** on `EXIT`/`INT`/`TERM`, and polls. On macOS it can fall back to **`open -a Ollama`** (no teardown when the script exits). **`OLLAMA_AUTOSTART=0`** means “must already be running.”
- **Example:** `./run.sh pull-model` runs `ollama pull` for `OPENAI_MODEL` or `llama3.1`.

### `setup_ollama.sh`

- **One sentence:** Installs the Ollama CLI when you use `--brew` on macOS, then pulls **`OPENAI_MODEL`** (default **`llama3.1`**) so local dev has a model without running the full Python **`setup`** first.
- **How:** Sources **`.env`** like **`run.sh`**, optionally runs **`brew bundle`** from **`Brewfile`**, checks for the **`ollama`** command, runs **`ollama pull`**, then probes **`http://127.0.0.1:11434/api/tags`** and prints a tip if nothing is listening yet.
- **Example:** `./setup_ollama.sh --brew` → Homebrew installs Ollama, then **`ollama pull llama3.1`** (or whatever **`OPENAI_MODEL`** is).

## Things that don't work well

- **Model capability gaps:** Smaller local models may ignore JSON formatting instructions or tool calls compared to large cloud models.
- **Search quality:** Zulip search and the agent’s query strategy affect recall; sparse keywords return few messages.
- **No Ollama:** Without a working install, auto-start cannot succeed; `./run.sh run` exits with hints unless checks are skipped (`SKIP_OLLAMA_CHECK=1`) or you only verify (`OLLAMA_AUTOSTART=0`).
- **Secrets:** Zulip credentials must be real; the LLM key can be a dummy for Ollama but not for real OpenAI-compatible hosts that enforce auth.

## Key metrics and results

- This project does not ship a fixed benchmark table. In practice, **latency** depends on hardware and model size; **quality** depends on the chosen **`OPENAI_MODEL`** and how much Zulip context you pass in.
