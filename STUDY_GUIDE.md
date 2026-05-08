# Study guide: Ask RC Zulip

## What we're building

- RC members ask a question in the app.
- The app searches **public Zulip**, calls an **LLM** (default: local Ollama), and returns a **structured summary** with **three sections** and **short inline quotes** linked to Zulip messages.

## How it works (high level)

1. **`/`** and **`/pair`** serve **`static/pair.html`** (Pair with RCers). **`/zulip`** serves **`static/zulip.html`** (Ask Zulip form + past conversations). A shared **top nav** on both pages links between them (full page loads, no iframe). **`conversation.html`** “New question” links to **`/zulip`**.
2. Web UI hits **`main.py`** (FastAPI, `/ask`).
3. **`agent.py`** runs **`messages_for_agent(question)`** once immediately (real Zulip HTTP), injects that as the first tool round in the chat log, then loops: more optional searches via tools, then a **JSON answer** with **`section_1`–`section_3`**.
4. **`zulip_search.py`** implements search and shapes each message for the model (including **sender** and **stream_id** when present). There is **no anonymization** in the pipeline (local/trusted use).
5. **`db.py`** stores SQLite history.

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
- **`runCLI.sh`** — For the **check-in terminal UI** only (no Ollama): ensures **`.venv`** and **`.env`**; if **`http://127.0.0.1:8000/api/checkin-pair`** already works, reuses that server; otherwise starts **`uvicorn main:app`** on **:8000** without **`--reload`**, waits until **`/api/checkin-pair`** responds, then runs **`node dist/cli.js`** from **`Rc-Checkins-TUI/rcAskZulip`**. On exit, stops the server **if this script started it**. If port **8000** is taken but the check-in URL fails, the script exits with an error (another process is blocking the port). The TUI hardcodes **`localhost:8000`**, so keep that port. **Node.js ≥ 22** and **npm** are required the first time ( **`npm ci`** + **`npm run build`** when **`dist/cli.js`** is missing).
- **`Rc-Checkins-TUI/`** — **Git submodule** ([Rc-Checkins-TUI](https://github.com/Tawfiqh/Rc-Checkins-TUI)): Ink + React CLI that **`fetch`**es **`GET http://localhost:8000/api/checkin-pair`**. The npm package lives in **`Rc-Checkins-TUI/rcAskZulip/`**. Clone this repo with **`git clone --recurse-submodules`**, or after clone run **`git submodule update --init --recursive`**. The CLI sends **no cookies**; use **`DEV_AUTH_BYPASS=1`** in **`.env`** locally so **`require_user`** accepts the request. You still need valid **`ZULIP_*`** (and related) settings for real check-in data.
- **`Ollama.sh`** — if **`ollama`** is not on **`PATH`**, runs **`setup_ollama.sh`** (when present). Then **`--ollama-only`** or full (Open WebUI). **`setup_ollama.sh`** — require Homebrew, then **`brew bundle`** (same **`Brewfile`** as **`install.sh --brew`**).

## Pair page (`/`, `/pair`)

**What it does:** Shows what RCers are currently working on (from their `#checkins` topic thread) grouped by topic, with one-click DM links and a copyable pairing message.

**How it works:**
1. `GET /api/checkin-pair` reads a precomputed snapshot from SQLite (`checkin_snapshot` table) — no Zulip or LLM calls on the request path. The response is `{grouped, generated_at}`.
2. A background asyncio task started in FastAPI's `lifespan` (`checkin_job.refresh_snapshot_loop`) rebuilds the snapshot every 12 hours. It runs in two LLM passes:
   - **Pass 1 — per-thread classification**: `checkin_fetch.build_grouped(zulip_site, classify_fn=classify_cached)` calls the LLM once per thread, asking for 2-5 broad labels. Per-thread results are cached in SQLite by SHA-256 of the input text, so unchanged check-ins are free on the next run.
   - **Pass 2 — consolidation**: if the result has more than 10 distinct buckets, `checkin_classifier.consolidate_buckets` calls the LLM **once** with the full unique label list ("Rust CLI", "Rust Borrow", "AI Agents", "LLM Tooling", …) and asks it to map every input label to a parent category (≤10). The mapping is cached by hash of the sorted label set + max count, so a stable label set re-uses the same result. Buckets are then re-grouped under parent names, with per-user dedupe so the same person doesn't appear twice in one parent.
   The result is written via `db.put_snapshot(...)`. On first boot (no snapshot yet) the endpoint falls back to a synchronous regex-classified build so the page isn't empty.
3. Inside `build_grouped` (run on the 12-hour schedule):
   1. `fetch_raw_checkins()` fetches up to 500 recent messages from the `#checkins` channel via Zulip API (no anonymization — real names and content are needed for the DM links and blurbs).
   2. Messages are sorted newest-first and `build_threads()` groups them by Zulip topic (`subject`). In this stream, each topic is the recurser's name, so each topic becomes one "person thread", capped at 80 newest threads.
   3. The thread owner is inferred by matching `sender_full_name` to the topic name. If no exact match is found, the newest message sender is used as a fallback DM target.
   4. The app keeps only messages authored by the inferred thread owner (the person whose topic it is). Replies from other people in that topic are excluded from classification.
   5. Owner-authored messages are combined, HTML is stripped, and a 200-char preview is built by `make_preview()`. This keeps richer context while avoiding "reply noise."
   6. The `classify_fn` is called with the preview + topic subject. By default this is `checkin_topics.classify()` (regex). The background job passes `checkin_classifier.classify_cached`, which: hashes the input text, checks the `classification_cache` SQLite table, and on a miss calls a local LLM (Ollama at `http://127.0.0.1:11434` by default) for 1-3 short Title-Case labels (e.g. `["Rust", "CLI Tools"]`). The result is cached by hash so repeated runs are fast. If the LLM call fails, it falls back to the regex classifier for that one entry and does **not** cache the fallback (so a recovered Ollama populates it next time).
   7. `dm_url()` constructs `{ZULIP_SITE}/#narrow/dm/{sender_id}` — opens a DM in the browser when the user is logged into Zulip.
   8. `checkin_near_url()` builds a **channel/topic/near/message** `#narrow` link from `stream_id`, `display_recipient` (stream name), topic subject, and the owner’s newest message `id` (Zulip’s `encode_hash_component` rules live in `encode_hash_component()`).
   9. Each API row includes **`avatar_url`** (from the anchor message) and **`checkin_url`** (empty if the Zulip payload lacks ids/stream info).
4. `static/pair.html` reads `payload.grouped` and shows `payload.generated_at` as a relative time ("Updated 3h ago"). It renders a **responsive card grid** with avatars (or initials), section **emoji**, **Open check-in** + **Open DM**, and **Copy opener**. Bucket **Other** is always **last**; unknown bucket names sort just before Other (LLM-emitted labels like "CLI Tools" are unknown to `BUCKET_ORDER` and get a default 📌 emoji).

**Key decisions:**
- **LLM classification with a 12-hour cached snapshot, regex fallback:** A local LLM (Ollama, `OPENAI_MODEL` / `llama3.1`) gives more nuanced labels than the hand-tuned regex (e.g. "Game Engines", "AI Agents"), but each call adds seconds. Calling it for ~80 threads on every page load would be unusable. We compute the grouped snapshot in a background asyncio task every 12 hours, store the result in the `checkin_snapshot` SQLite table, and serve it from there in O(1) reads. Per-thread results are also cached by SHA-256 of the input text in `classification_cache`, so repeated runs only LLM-classify *new* check-in content. Trade-off: page data can be up to 12 hours stale, and the very first run on a fresh DB pays full LLM cost (~minutes). On cold start we fall back to the synchronous regex build so users aren't staring at an empty page.
- **Two-pass classification (per-thread, then consolidation):** The first pass produces specific labels per check-in (e.g. "Rust CLI", "Rust Borrow"), which on its own creates too many one-person buckets in the UI. A second LLM pass takes the full unique label set and groups it into ≤10 parent categories ("Systems", "AI", "Web"…). The mapping is cached by sorted-label hash so it only re-runs when the label vocabulary actually changes. Trade-off: the consolidation is one extra LLM call per refresh and depends on the LLM grouping consistently; if it fails, we fall back to the unconsolidated (potentially-many-bucket) view rather than crashing.
- **Keyword buckets as fallback:** When Ollama is unreachable, individual entries fall back to `checkin_topics.classify()` (regex) so the page never goes fully empty. Trade-off: a partial Ollama outage produces a mix of LLM and regex labels in the same snapshot until the next refresh.
- **Multi-label classification (not first-match only):** One check-in can belong to several topics (for example Python + Cloud + DevOps), which improves pairing discovery for people doing cross-domain work. Trade-off: the same person can appear in multiple sections, so the UI can look more repetitive.
- **Topic-thread aggregation over single-message dedupe:** We classify from the person's own updates in their check-in thread (topic) instead of one latest message. This improves signal when work spans several updates.
- **Owner-only classification input:** Replies from other people in someone else's topic are ignored for categorization. This prevents cross-talk from mislabeling a person's interests. Trade-off: useful context from collaborators is not used.
- **No anonymization:** This endpoint reveals real names and work topics. It's equivalent to browsing `#checkins` while logged in, but centralised. Do not expose the server without auth if deploying broadly.
- **`sender_id` for DM links (not email):** Zulip's `/#narrow/dm/{id}` pattern works without knowing the user's email. It opens their DM thread in the org you're logged into.
- **`ZULIP_CHECKIN_STREAM` env var:** Defaults to `"checkins"`. Swap it to `"alumni checkins"` or another stream without code changes.
- **Batch scoping TBD:** The MVP uses anyone with a recent check-in. A future enhancement could filter by a Zulip user group (`ZULIP_BATCH_USER_GROUP_ID`) to show only current-batch members.
## Authentication (RC OAuth)

**What it does:** Gates the entire app behind Recurse Center login. Only RC members (current or alum) can use it. Unauthenticated visitors see a landing page.

**How it works (the OAuth 2.0 authorization-code flow):**
1. User hits `/`. `_serve_app_or_landing()` checks `request.session["user"]` — empty, so we serve `static/landing.html`.
2. User clicks "Login with Recurse Center". `GET /login` calls Authlib's `oauth.recurse.authorize_redirect(...)`, which builds a URL like `https://www.recurse.com/oauth/authorize?client_id=...&redirect_uri=...&response_type=code&state=<random>` and stores `state` in the session (a CSRF guard).
3. RC asks the user to grant permission, then redirects back to `/auth/callback?code=<short-lived>&state=<same>`.
4. `auth_callback` calls `oauth.recurse.authorize_access_token(request)`, which validates `state`, POSTs `code` to `https://www.recurse.com/oauth/token`, and gets back `{access_token, refresh_token, expires_in: 7200, ...}`.
5. We then `GET /api/v1/people/me` with the bearer token, store `{id, name, email, image_path}` in `session["user"]` and the full token dict in `session["token"]`, and redirect to `/`.
6. On every protected route, the `require_user` dependency reads the session and calls `get_valid_token()`, which auto-refreshes when the access token has < 60s of life left.

**Token refresh:** RC's refresh tokens are *single-use* — each refresh returns a new pair. `get_valid_token()` writes both new values back into the session. If RC rejects the refresh (`invalid_grant` — user revoked access, or refresh expired), we clear the session and return 401. Concurrent in-flight refreshes from the same browser would race and invalidate each other; acceptable for this app's traffic but worth knowing.

**Why session cookies (not JWTs):** Starlette's `SessionMiddleware` signs a small server-side payload with `SESSION_SECRET` and stores it as an opaque cookie. Logout is just `session.clear()` — instant revocation. JWTs would require a separate denylist.

**Dev bypass (`DEV_AUTH_BYPASS`):** For local work without RC OAuth credentials, set `DEV_AUTH_BYPASS` to `1`, `true`, or `yes`. `auth.current_user` and `auth.require_user` then return a fixed stub user (optional `DEV_AUTH_BYPASS_NAME` for the label in the UI). No session token is created; RC API calls from OAuth are skipped. **Never set this in production** — it removes the gate entirely.

**Why Authlib (not the official RC Python SDK):** The Stainless-generated SDK calls RC API endpoints once you have a token; it doesn't implement the redirect/state/callback flow a web app needs. Authlib does, natively for Starlette/FastAPI.

**Required env vars:** `RC_CLIENT_ID`, `RC_CLIENT_SECRET`, `RC_REDIRECT_URI`, `SESSION_SECRET`. See `.env.example`.

## Things that don't work well

- Small local models are weaker at tools/JSON than big cloud APIs.
- Zulip recall depends on search quality and your query.
- `OPENAI_BASE_URL` on localhost with Ollama down → failed requests until **`./Ollama.sh`**, the desktop app, or **`ollama serve`** is running.
- Zulip credentials are real secrets; the model sees real names and message text.
- OAuth refresh-token races: with single-use refresh tokens, two concurrent expired-token requests from the same session can invalidate each other and force a re-login. No locking is implemented because traffic is one-user-clicking-around.
- `RC_REDIRECT_URI` must match the redirect URI registered on recurse.com *exactly* (scheme, host, port, path). Mismatches surface as opaque OAuth errors.

## Key metrics and results

- No fixed benchmark in the repo.
- **Latency** and **quality** depend on hardware, `OPENAI_MODEL`, and how much Zulip context you pass in.

## Deployment (Disco)

### What changes for Disco

- Disco expects two repo-root files: `disco.json` and `Dockerfile`.
- `disco.json` tells Disco which service port the app listens on (`8080`).
- The container starts `uvicorn` directly on `0.0.0.0:8080` so traffic from the Disco reverse proxy can reach it.

### Production OAuth setup (RC login)

- Keep using the same RC OAuth flow (`/login` -> `/auth/callback`), but update env values for the deployed domain.
- Register `https://<your-domain>/auth/callback` in RC app settings and set `RC_REDIRECT_URI` to the exact same value.
- Set `SESSION_COOKIE_SECURE=true` in production so the browser only sends session cookies over HTTPS.
- Keep `DEV_AUTH_BYPASS=0` (or unset) in production. Think of this like "leave the side door locked."

### LLM setup in containers

- Local default is `OPENAI_BASE_URL=http://localhost:11434/v1` (Ollama).
- In Disco, `localhost` usually points to the app container itself, not your laptop.
- For production, point `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` to a reachable API endpoint.
- Analogy: local Ollama is like a printer plugged into your desk; production needs a network printer everyone can reach.

### Data persistence tradeoff

- Conversations are saved in `conversations.db` (SQLite file in the working directory).
- If container storage is ephemeral, redeploys can wipe that file.
- This is simple and fast for MVPs, but weak for long-term history.
- Better long-term option: attach persistent storage (if available) or move to a managed database.
