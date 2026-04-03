# Ask RC Zulip

A small web app for [Recurse Center](https://www.recurse.com/) participants: ask what RCers think about a topic, search public Zulip conversations, and get an AI summary with citations.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Python 3.12+ (see `.python-version`)
- A Zulip API key with access to the RC organization’s public streams
- An OpenAI API key

## Setup

1. Clone the repo and enter the directory.

2. Create a `.env` file in the project root:

   ```env
   OPENAI_API_KEY=sk-...
   ZULIP_SITE=your-org.zulipchat.com
   ZULIP_EMAIL=your-bot-or-account@example.com
   ZULIP_API_KEY=...
   ```

3. Install dependencies:

   ```bash
   ./dev.sh setup
   ```

   Or: `uv sync`

## Run

```bash
./dev.sh run
```

Or: `uv run python main.py`

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) (default uvicorn port). Submit a question on the home page; the app searches Zulip, runs an agentic loop with GPT-4o, and shows the answer with linked message excerpts.

## How it works (briefly)

- **Backend:** [FastAPI](https://fastapi.tiangolo.com/) (`main.py`) serves static pages and JSON APIs.
- **Search:** `zulip_search.py` calls Zulip’s message API with a public-channels narrow and full-text search; results are deduplicated across queries.
- **Privacy:** `anonymize.py` strips sender identity from what the model sees and normalizes mentions (see code for check-in stream handling).
- **Agent:** `agent.py` uses the OpenAI API (tools + structured JSON output) to run searches and produce a final answer with `message_ids` for citations.
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
| `NOTES.md` | Product notes and future ideas |
