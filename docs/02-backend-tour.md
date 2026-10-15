# Backend tour

Python 3.11+, FastAPI, Playwright, SQLite via `aiosqlite`. Everything is `async`: one process runs the
web API, the scheduler, three workers and the live-event bus on one event loop. Files are listed
roughly in the order a request flows through them.

## Start-up and plumbing

| File | Purpose | Key pieces | Connects to |
|---|---|---|---|
| `app/main.py` | Creates the FastAPI app and wires everything together | `lifespan()` starts the DB, resets stuck targets, launches Chromium, starts the workers and the scheduler (and stops them in reverse). `spa()` serves the built React app with an `index.html` fallback. | every router; `fetcher`, `jobqueue`, `scheduler` |
| `app/config.py` | All settings from environment variables | `Settings` (pydantic-settings), `minutes_to_seconds()` (respects `DEBUG_FAST_SCHEDULE`), `data_path()` | everything |
| `app/db.py` | One shared SQLite connection, schema and helpers | `MIGRATIONS` (ordered SQL scripts) + `schema_version`; `connect()` turns on WAL and foreign keys; `fetch_one/fetch_all/execute`; `insert_unique()` returns `None` on a UNIQUE clash (used for alert dedupe) | all data access |
| `app/schemas.py` | The API contract as Pydantic models | `WatchSummary`, `WatchDetail`, `SnapshotItem`, `CompareResult`... FastAPI turns them into OpenAPI, which the frontend turns into TypeScript | routes, frontend `schema.d.ts` |
| `app/errors.py` | One error shape for the whole API | `ApiError(status, code, message)`; handlers turn every error into `{"error": {"code", "message"}}` | routes |
| `app/views.py` | Builds response shapes from rows | `watch_summary()`, `watch_detail()`, `snapshot_item()`, `WATCH_SELECT` (one query with version and watcher counts) | routes |

## Accounts and safety

| File | Purpose | Key pieces |
|---|---|---|
| `app/auth.py` | Passwords and sessions | Argon2 `hash_password()/verify_password()`; `set_session_cookie()` signs `{uid}` with itsdangerous into an HttpOnly cookie; `current_user()` and `admin_user()` dependencies |
| `app/routes/auth.py` | `/api/auth/signup`, `/login`, `/logout`, `/me` | First account (or `ADMIN_EMAIL`) becomes admin; login is limited to 10 attempts per minute per IP; the same message for "no such email" and "wrong password" |
| `app/security.py` | SSRF guard, CSRF Origin check, rate limits | `is_public_ip()`, `resolve_host()` (5-minute DNS cache), `check_url_is_public()`, `is_allowed_subrequest()` (used for every browser request), `is_demo_url()` (the only exception: our own `/demo/*`), `OriginCheckMiddleware`, `RateLimiter` (sliding window) |
| `app/urlnorm.py` | URL validation and normalisation | `normalise_url()` (https default, lowercase host, drop default ports, fragments and `utm_*/fbclid/gclid/ref`, sort query, strip trailing slash), `dial_seed()` (first 8 hex digits of SHA-256), `registrable_domain()` (tldextract, offline) |

## The engine

| File | Purpose | Key pieces |
|---|---|---|
| `app/scheduler.py` | Decides *when* | `Scheduler.tick()` every 20 s enqueues targets whose `next_fetch_at` passed and that have an un-paused watch. `jittered()` adds ±10%. Also starts the queue heartbeat (SSE every 3 s), the digest loop and the cleanup loop. `reset_stuck_targets()` runs at startup. |
| `app/jobqueue.py` | The queue and workers | `JobQueue.enqueue()` (priority 0 = a person is waiting, 1 = scheduled; dedupes queued and running targets), `_worker()`, `_run_with_retries()` (3 attempts, backoff 5/20/60 s + jitter, retry only retryable failures), `AttemptResult` |
| `app/politeness.py` | Not hammering sites (Q4) | `slot(url)` is an async context manager holding a per-domain lock and enforcing a minimum gap (10 s, or the site's Crawl-delay if larger). `robots_allows()` caches robots.txt for 24 h. `defer()` honours Retry-After. `snapshot()` feeds /system. |
| `app/fetcher.py` | Rendering + classification (R1, Q1) | `Fetcher` owns one Chromium and relaunches it if it crashes. `render()` caps at 45 s and uses a fresh context per check, the honest user agent `ChangeWatchBot/1.0`, and blocks fonts, media and ad hosts plus private sub-requests. Collects HTML, title, an 8000 px-capped screenshot and element boxes. `_classify_status()` and `_looks_like_bot_wall()` decide ok/error/blocked. |
| `app/extract.py` | HTML → clean text (R3) | `extract()` (noise removal → picked regions → text), `remove_noise()`, `element_text()` (blocks become line breaks; keeps `img alt`), `css_path()` and `element_for_line()` (used to learn element rules), `learning_soup()` |
| `app/noise.py` | Every anti-noise layer (R4, Q3) | `NOISE_SELECTORS` / `CAROUSEL_SELECTORS`; `RULES` (regexes; dates are blanked only within 2 days of the check); `normalise_text()` (raw and normalised lines stay aligned); `line_signature()`; `measure_change()` and `is_significant()` (sensitivity thresholds); `stricter()`; `is_oscillating()` (A→B→A→B) |
| `app/checker.py` | One check, start to finish | `check_target()` → `_check()`: SSRF → robots → optional 304 pre-check (`conditional_unchanged`) → render → classify → `handle_success()`: evaluate every due watch (`evaluate_text`, `compare_with_baseline`), confirmation re-fetch + `learn_rules()` + `common_change()`, `create_snapshot()`, `record_number()`, `after_change()` (flapping, AI summary, SSE, alerts). `apply_failure()` handles errors and backoff. `rebaseline()` runs after you pick regions. |
| `app/differ.py` | Text diff (R6) | `diff_lines()` runs SequenceMatcher on normalised lines, shows raw lines, and does a word-level diff inside edited pairs (`word_diff()`). `changed_lines_preview()` feeds alerts. |
| `app/visual_diff.py` | Screenshot diff (R6) | `detect_shift()` (finds vertical movement on 4× smaller copies), `compare_images()` (difference → threshold → dilate → 16 px cells → flood fill → regions, red-box image), `cached_compare()`, `save_crop()`, `save_thumbnail()` |
| `app/numbers.py` | Number tracking (bonus) | `parse_number()` (₹1,23,456.50, $1,234.56, 1.234,56 €, 12K, 1.2M, −4.5%), `extract_number()` (selector and/or regex) |
| `app/summarize.py` | One-line summaries (bonus) | `heuristic_summary()` (counts lines, quotes the most informative); `ai_summary()` (raw httpx call to Anthropic's Messages API, 15 s timeout, falls back on any problem) |
| `app/alerts.py` | Email, Telegram, Discord (R7) | `claim()` inserts the row with a UNIQUE `dedupe_key` first; `deliver()` sends with 3 retries; `on_change()`, `on_status()` (one per watch/status/day + "back to normal"), `on_flapping()`, `on_threshold()`, `send_test()`; `valid_discord_webhook()` blocks SSRF via webhook URLs |
| `app/digest.py` | Daily digest | `send_digest()` groups `queued_digest` rows once per local day after your chosen hour; `digest_loop()` runs every 10 minutes |
| `app/events.py` | In-process pub/sub for SSE | `EventBus.subscribe()` gives one queue per open tab; `publish()` sends to one user; `broadcast()` sends to everyone (aggregate data only) |
| `app/maintenance.py` | Housekeeping | `cleanup_once()` deletes unreferenced fetch files older than 7 days and old diff images |
| `app/media.py` | Serving images safely | Screenshots, crops, thumbnails and diff images, only if you watch the page they came from |
| `app/rss.py` | Per-watch RSS 2.0 feed | `/rss/{token}.xml`: latest 30 versions, compare links, RFC 822 dates |
| `app/demo.py` | The demo page | Fresh timestamp, token, counter, random tip and rotating banner on every load; the real notice changes every 5 minutes |
| `app/seed.py` | Demo data | `python -m app.seed` creates `demo@changewatch.app` with 5 real pages (no fake snapshots) |
| `app/picker/frame.py` | Safe snapshot for the picker | `sanitise()` strips scripts, handlers, iframes and `javascript:` URLs, adds `<base href>`, and injects `picker.js` with a CSP nonce; `build_csp()` |
| `app/picker/picker.js` | Runs inside the sandboxed iframe | Hover outline, `selectorFor()` (stable id → stable attribute → `tag.class` path with `:nth-of-type` only when needed), `postMessage` protocol, ArrowUp/Enter/Esc |

## Routes

| File | Endpoints |
|---|---|
| `routes/watches.py` | `GET/POST /api/watches`, `GET/PATCH/DELETE /api/watches/{id}`, `POST .../check` (2-minute cooldown), `.../snapshots`, `/api/snapshots/{id}`, `.../compare`, `.../checks`, `.../numbers`, `DELETE .../volatile-rules/{i}`, `.../rss/regenerate`, `.../share` |
| `routes/picker.py` | `.../picker/session`, `.../picker/frame` (CSP header), `.../picker/test`, `PUT .../selectors` (saves + re-baselines + checks) |
| `routes/settings.py` | `GET/PUT /api/settings`, `POST /api/settings/test-alert` |
| `routes/stats.py` | `/api/stats/overview`, `/api/activity` (changes, plus problems once per run), `/api/admin/stats` |
| `routes/templates.py` | `GET /api/templates/{token}`, `POST .../import` |
| `routes/events.py` | `GET /api/events` (SSE; `ping` every 15 s) |
| `routes/public.py` | `POST /api/url/preview`, `/healthz`, `/robots.txt`, `/bot`, `/demo/changing-page`, `/demo/bot-check`, `/demo/outage` |

## Database tables (SQLite)

`users`, `targets` (one per URL; `next_fetch_at` indexed; `volatile_rules` JSON), `fetches` (one per
render; files on disk), `watches` (one per user × target), `snapshots` (one per real version; both
`text` and `raw_text`), `alerts` (UNIQUE `dedupe_key`), `number_points`, `check_log` (last 500 per
target), `templates`. Timestamps are ISO-8601 UTC strings.

## Tests (`backend/tests/`)

`test_noise.py` covers every normalisation rule, prices left alone, sensitivity levels and flapping.
`test_core.py` covers URL normalisation, SSRF, the text and visual diffs, number parsing, keywords,
extraction, selectors and classification. `test_alerts.py` covers dedupe across retries and 5
concurrent claims, and Discord webhook validation. Run `cd backend && .venv/bin/pytest -q`.
