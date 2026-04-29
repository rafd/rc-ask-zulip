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
- **Cons:** tool/JSON behavior depends on the server; for localhost Ollama, something must serve **:11434** (**`./Ollama.sh`**, desktop app, or **`ollama serve`**).

## How each piece works

- **`main.py`** — Routes, static files, `/config` (Zulip site for links), save chats.
- **`agent.py`** — Bootstrap tool round, chat loop, validates JSON; repair pass on failure.
- **`zulip_search.py`** — `ZULIP_*` env, search public streams, `prepare_for_agent`.
- **`anonymize.py`** — Not used by the app (legacy).
- **`db.py`** — SQLite persistence.
- **`install.sh`** — `uv sync`, optional `--brew`.
- **`run.sh`** — **`install.sh`** if **`.venv`** is missing; loads **`.env`**; **`curl`** **`${OLLAMA_HOST:-http://127.0.0.1:11434}/api/tags`** and runs **`./Ollama.sh --ollama-only`** if that fails; **`exec`** **`main.py`** on **:8000**.
- **`Ollama.sh`** — if **`ollama`** is not on **`PATH`**, runs **`setup_ollama.sh`** (when present). Then **`--ollama-only`** or full (Open WebUI). **`setup_ollama.sh`** — require Homebrew, then **`brew bundle`** (same **`Brewfile`** as **`install.sh --brew`**).

## Pair page (`/pair`)

**What it does:** Shows what RCers are currently working on (from their `#checkins` topic thread) grouped by topic, with one-click DM links and a copyable pairing message.

**How it works:**
1. `GET /api/checkin-pair` calls `checkin_fetch.build_grouped(zulip_site)`.
2. `fetch_raw_checkins()` fetches up to 400 recent messages from the `#checkins` channel via Zulip API (no anonymization — real names and content are needed for the DM links and blurbs).
3. Messages are sorted newest-first and `build_threads()` groups them by Zulip topic (`subject`). In this stream, each topic is the recurser's name, so each topic becomes one "person thread", capped at 75 newest threads.
4. The thread owner is inferred by matching `sender_full_name` to the topic name. If no exact match is found, the newest message sender is used as a fallback DM target.
5. The app keeps only messages authored by the inferred thread owner (the person whose topic it is). Replies from other people in that topic are excluded from classification.
6. Owner-authored messages are combined, HTML is stripped, and a 200-char preview is built by `make_preview()`. This keeps richer context while avoiding "reply noise."
7. `checkin_topics.classify()` matches the owner-only preview + topic subject against regex keyword buckets and returns all matches in bucket order. If nothing matches, it returns `["Other"]`.
8. `dm_url()` constructs `{ZULIP_SITE}/#narrow/dm/{sender_id}` — opens a DM in the browser when the user is logged into Zulip.
9. `checkin_near_url()` builds a **channel/topic/near/message** `#narrow` link from `stream_id`, `display_recipient` (stream name), topic subject, and the owner’s newest message `id` (Zulip’s `encode_hash_component` rules live in `encode_hash_component()`).
10. Each API row includes **`avatar_url`** (from the anchor message) and **`checkin_url`** (empty if the Zulip payload lacks ids/stream info).
11. `static/pair.html` renders a **responsive card grid** with avatars (or initials), section **emoji**, **Open check-in** + **Open DM**, and **Copy opener**. Bucket **Other** is always **last**; unknown bucket names sort just before Other.

**Key decisions:**
- **Keyword buckets over LLM clustering:** Fast, zero-cost, easy to tune. Trade-off: imprecise — "music" can contain keywords from other buckets, so regex uses `\b` word boundaries. LLM clustering would be more accurate but adds latency and cost.
- **Multi-label classification (not first-match only):** One check-in can belong to several topics (for example Python + Cloud + DevOps), which improves pairing discovery for people doing cross-domain work. Trade-off: the same person can appear in multiple sections, so the UI can look more repetitive.
- **Topic-thread aggregation over single-message dedupe:** We classify from the person's own updates in their check-in thread (topic) instead of one latest message. This improves signal when work spans several updates.
- **Owner-only classification input:** Replies from other people in someone else's topic are ignored for categorization. This prevents cross-talk from mislabeling a person's interests. Trade-off: useful context from collaborators is not used.
- **No anonymization:** This endpoint reveals real names and work topics. It's equivalent to browsing `#checkins` while logged in, but centralised. Do not expose the server without auth if deploying broadly.
- **`sender_id` for DM links (not email):** Zulip's `/#narrow/dm/{id}` pattern works without knowing the user's email. It opens their DM thread in the org you're logged into.
- **`ZULIP_CHECKIN_STREAM` env var:** Defaults to `"checkins"`. Swap it to `"alumni checkins"` or another stream without code changes.
- **Batch scoping TBD:** The MVP uses anyone with a recent check-in. A future enhancement could filter by a Zulip user group (`ZULIP_BATCH_USER_GROUP_ID`) to show only current-batch members.
## Things that don't work well

- Small local models are weaker at tools/JSON than big cloud APIs.
- Zulip recall depends on search quality and your query.
- `OPENAI_BASE_URL` on localhost with Ollama down → failed requests until **`./Ollama.sh`**, the desktop app, or **`ollama serve`** is running.
- Zulip credentials are real secrets; the model sees real names and message text.

## Key metrics and results

- No fixed benchmark in the repo.
- **Latency** and **quality** depend on hardware, `OPENAI_MODEL`, and how much Zulip context you pass in.
