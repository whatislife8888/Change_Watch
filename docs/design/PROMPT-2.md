# Build ChangeWatch — a luxury Website Change Detector (VinnovateIT Round 1)

You are building a complete, working, deployable product from an empty folder called `changewatch/`. It has **two apps that work together**: a Python **backend** and a React **frontend**. Read this entire document before writing any code.

I am a first-year B.Tech CSE student. Evaluators will question me about this code, so **you must explain everything you build** in simple language (Section 15 is mandatory, not optional).

---

## 0. How you must work

1. Read the whole document first. Then look at `docs/design/dial-reference.png` (I put it there) — it shows what the signature dials should look like.
2. Create `CLAUDE.md` at the repo root first (contents in Section 15.5) so these rules persist across sessions.
3. Work **phase by phase** (Section 17). At the start of each phase run `date` to check the time against the plan. After each phase: run it, test it, take UI screenshots if there is UI, fix problems, **commit** with a clear message, and **explain the phase to me** (Section 15.2).
4. Priorities, given the deadline of **15 Oct 2026, 11:59 PM IST**:
   1. All 8 core requirements working end to end.
   2. The 4 design questions solved in code and explained.
   3. The premium design system applied to every screen from the start (not bolted on at the end) — plus the signature dials.
   4. Bonus features.
   5. Extra polish.
   **Deploy a working version by about 7:30 PM IST no matter what**, then keep improving and redeploying.
5. Don't stop to ask me questions unless you're truly blocked. Choose a sensible default, write the decision in `docs/BUILD-LOG.md`, and keep going.
6. Never commit secrets. Never fake functionality (no hard-coded "demo" data pretending to be real results, except the seed script in 11.6).
7. Prefer **clear code over clever code**. I need to be able to explain every file.

---

## 1. The task (verbatim from the brief)

**Goal:** Build a service that monitors public web pages and alerts users to meaningful changes while ignoring noise.

**Core requirements**
1. Users add a URL, name and check interval (15 min to 24 h); pages render in a headless browser (Playwright/Puppeteer).
2. Checks run through a scheduler and job queue with timeouts and retries; public pages only, no stored credentials.
3. Each check saves page text and a screenshot; a new snapshot is stored only when the content hash changes.
4. Noise filtering for timestamps, counters, ads, rotating banners and random tokens, plus a sensitivity setting.
5. Visual picker to select regions to watch (saved as CSS selectors) and regions to ignore.
6. Text diff, highlighted screenshot diff and side-by-side comparison of any two versions.
7. Alerts via email and Telegram/Discord webhook with summary and diff link; no duplicates; optional daily digest.
8. Per-page version timeline and a dashboard with last checked, last changed and status (OK, error, blocked).

**Design questions (answer them in code AND in the docs)**
1. Is a site outage or CAPTCHA a change?
2. If 200 users watch the same URL, is it fetched 200 times?
3. How to avoid endless alerts on pages that differ on every load?
4. How to avoid hammering a site with requests?

**Bonus (build these):** keyword-only alerts, number tracking with charts, AI one-line change summaries, per-page RSS feed. (Skip the browser extension.)

Evaluation favours originality, depth, multi-user interaction and reliability over basic functionality.

---

## 2. Repository layout and how the two apps work together

```
changewatch/
├── backend/                 Python: FastAPI + Playwright + SQLite (the engine and the API)
├── frontend/                React + Vite + TypeScript (everything the user sees)
├── docs/                    Explanations, Q&A, demo script, design reference, build log
│   └── design/dial-reference.png
├── CLAUDE.md                Standing rules for Claude Code (you create it)
├── README.md
├── Dockerfile               Multi-stage: builds the frontend, runs the backend, which serves it
├── railway.json
├── dev.sh                   Starts backend (port 8000) and frontend (port 5173) together
└── .gitignore               Ignores .env, data/, node_modules/, dist/, __pycache__/, .venv/
```

**How they talk**
- The frontend never touches the database. It only calls the backend's JSON API under `/api/...` and receives live updates through **Server-Sent Events** at `/api/events`.
- **Development:** Vite runs on `localhost:5173` and proxies `/api`, `/rss`, `/demo`, `/healthz` and `/bot` to the backend on `localhost:8000`. Because the browser only ever talks to 5173, cookies work and no CORS setup is needed.
- **Production:** one Docker container. The Docker build compiles the frontend into static files; FastAPI serves them at `/` with an SPA fallback (any non-API GET that isn't a file returns `index.html`), and the API stays at `/api`. One URL, one service, one deploy.
- **Optional split hosting** (frontend on Vercel/Netlify, backend on Railway): support it through env vars (`CORS_ORIGINS` on the backend, `VITE_API_BASE` on the frontend, cookies `SameSite=None; Secure`). Document it, but default to the single container.
- **One source of truth for data shapes:** backend response models live in `backend/app/schemas.py` (Pydantic). FastAPI publishes OpenAPI at `/api/openapi.json` (docs at `/api/docs`). Add `npm run gen:api` in the frontend that generates `src/api/schema.d.ts` with `openapi-typescript` from the running backend, and build `src/api/types.ts` on top of it, so the two apps can't drift apart.

### 2.1 Backend structure
```
backend/
├── app/
│   ├── main.py            FastAPI app, startup/shutdown (browser, scheduler, workers), routers, SPA serving
│   ├── config.py          Settings from env vars (pydantic-settings)
│   ├── db.py              aiosqlite connection, WAL mode, schema + migrations
│   ├── schemas.py         Pydantic request/response models (the API contract)
│   ├── auth.py            Signup/login/logout, password hashing, session cookie, current_user dependency
│   ├── security.py        SSRF guard, Origin check for unsafe methods, login rate limit
│   ├── urlnorm.py         URL validation + normalisation + dial seed
│   ├── fetcher.py         Playwright browser, render(), screenshots, element boxes, result classification
│   ├── politeness.py      Per-domain rate limiter, robots.txt cache, Retry-After/backoff state
│   ├── jobqueue.py        Priority job queue, workers, timeouts, retries
│   ├── scheduler.py       Tick loop that finds due targets and enqueues them (with jitter)
│   ├── extract.py         Apply watch/ignore selectors, HTML → clean text
│   ├── noise.py           Normalisation rules, volatility learning, sensitivity, flapping
│   ├── differ.py          Line + word diff, structured diff ops
│   ├── visual_diff.py     Screenshot diff, changed regions, shift detection, thumbnails
│   ├── checker.py         One target check → evaluate every watch on it → snapshots → alerts → events
│   ├── alerts.py          Email, Telegram, Discord, dedupe, retries, status alerts
│   ├── digest.py          Daily digest task
│   ├── summarize.py       AI one-line summary + heuristic fallback
│   ├── numbers.py         Number extraction for tracking
│   ├── rss.py             Per-watch RSS feed
│   ├── events.py          In-process event bus for SSE
│   ├── media.py           Serving screenshots/crops/diff images with permission checks
│   ├── demo.py            /demo/changing-page test page
│   ├── seed.py            Demo user + sample watches (python -m app.seed)
│   ├── picker/            picker.js, picker.css, frame.py (sanitised snapshot for the visual picker)
│   └── routes/            auth.py, watches.py, snapshots.py, compare.py, picker.py, settings.py,
│                          stats.py, events.py, templates.py, public.py
├── tests/                 pytest: noise rules, sensitivity, diff, dedupe, url normalisation, SSRF, numbers
├── requirements.txt       Pinned versions
└── .env.example
```

### 2.2 Frontend structure
```
frontend/
├── index.html
├── package.json
├── vite.config.ts         Dev proxy: /api, /rss, /demo, /healthz, /bot → http://localhost:8000
├── tsconfig.json          strict: true
├── .env.example           VITE_API_BASE= (empty = same origin)
├── public/favicon.svg     A tiny guilloché dial
└── src/
    ├── main.tsx, App.tsx  Providers (QueryClient, Router, Theme), routes, layout
    ├── api/               client.ts (fetch wrapper), schema.d.ts (generated), types.ts, hooks.ts (TanStack Query)
    ├── realtime/          useEvents.ts (SSE → cache invalidation, toasts, dial re-engrave)
    ├── design/            tokens.css (both themes), global.css, textures.css, motion.ts (easings, durations)
    ├── components/
    │   ├── dial/          guilloche.ts, Dial.tsx, SweepHand.tsx, Jewel.tsx, DateWindow.tsx, useSpecular.ts
    │   ├── movement/      Movement.tsx, gears.ts
    │   ├── loupe/         Loupe.tsx
    │   ├── odometer/      Odometer.tsx
    │   ├── diff/          UnifiedDiff.tsx, SideBySideDiff.tsx, ScreenshotDiff.tsx, SliderCompare.tsx, OverlayCompare.tsx
    │   ├── timeline/      Timeline.tsx
    │   ├── charts/        NumberChart.tsx, Sparkline.tsx
    │   ├── layout/        TopBar.tsx, ThemeSwitch.tsx, SoundToggle.tsx, PageShell.tsx
    │   └── ui/            Button, Input, Select, SegmentedControl, Tabs, Modal, Menu, Toast styling,
    │                      Skeleton, EmptyState, StatusText, Tooltip
    ├── pages/             Landing, Login, Signup, Dashboard, AddPage, PageDetail, Compare, Picker,
    │                      Activity, Settings, System, ImportTemplate, NotFound
    └── lib/               time.ts (relative + timezone formatting), sound.ts (Web Audio), cache.ts
```

---

## 3. Tech stack (fixed — don't switch)

**Backend:** Python 3.11+, FastAPI, Uvicorn, Playwright for Python (async, Chromium), SQLite via `aiosqlite` (WAL on), Pillow, BeautifulSoup4 + lxml, httpx, `difflib`, `argon2-cffi` (password hashing), `itsdangerous` (signed session cookie), `sse-starlette`, `pydantic-settings`, `tldextract` (use its bundled suffix list, no network: `TLDExtract(suffix_list_urls=())`), pytest + pytest-asyncio. Scheduler and job queue are **built in-process with asyncio** (no Redis/Celery), behind a small class so Redis could replace it later.

**Frontend:** React 18+, Vite, TypeScript (strict), React Router, TanStack Query, **Motion** (the `motion` package, formerly Framer Motion; import from `motion/react`), Recharts (custom-styled), Sonner (custom-styled toasts), `@phosphor-icons/react` (light/thin weights only), Lenis (smooth scroll on the landing page only), clsx, openapi-typescript. Styling: **CSS Modules + design tokens as CSS variables**. **No Tailwind and no component library** (no MUI, shadcn, Bootstrap, Chakra) — every component is custom so the look is unique.

**Deploy:** Docker (official Playwright Python image) on Railway with a persistent volume at `/data`. Not Vercel for the backend — serverless can't run a headless browser plus a long-running scheduler.

---

## 4. Core architecture: Targets vs Watches (the key idea)

Separate **what gets fetched** from **who is watching it**:
- A **Target** is one normalised URL. The system fetches it on a schedule. There is exactly **one Target per normalised URL**, however many users watch it.
- A **Watch** is one user's subscription to a Target: their own name, interval, watch/ignore selectors, sensitivity, keywords, number tracking and alert channels.
- One fetch of a Target produces one rendered HTML + one full-page screenshot (+ element boxes). **Every Watch on that Target is evaluated from that same fetch**, each with its own selectors and noise rules, producing its own content hash, snapshots and alerts.
- A Target's effective interval = the **minimum** interval among its active Watches (never below 15 min). A Watch is evaluated on a fetch only if its own interval is due.

This answers design question 2: 200 users watching one URL → one fetch per cycle.

---

## 5. Database (SQLite)

Timestamps as ISO-8601 UTC strings. Use a `schema_version` table and an ordered list of migrations so restarts never break the DB.

- **users**: id, email (unique), password_hash, display_name, timezone (default `Asia/Kolkata`), digest_mode (`instant`|`daily`), digest_hour (0–23, default 9), last_digest_date, telegram_chat_id, telegram_bot_token (nullable; optional per-user bot), discord_webhook_url, is_admin, created_at
- **targets**: id, url (normalised, unique), domain, dial_seed, status (`ok`|`error`|`blocked`|`pending`), last_fetched_at, next_fetch_at, running_since, consecutive_failures, last_error, last_http_status, etag, last_modified, volatile_rules (JSON), created_at — index on next_fetch_at
- **fetches**: id, target_id, fetched_at, http_status, final_url, html_path (gzipped), screenshot_path, page_width, page_height, element_boxes (JSON: selector → box), duration_ms
- **watches**: id, user_id, target_id, name, interval_minutes (15..1440), watch_selectors (JSON list; empty = whole page), ignore_selectors (JSON), ignore_carousels (bool, default true), sensitivity (`low`|`medium`|`high`), keywords (JSON), keyword_mode (`off`|`appear`|`disappear`|`any`), number_selector, number_regex, number_thresholds (JSON), alert_email, alert_telegram, alert_discord (bools), paused, status, status_message, last_checked_at, last_changed_at, next_due_at, last_content_hash, flapping_until, rss_token (unique), created_at — index on target_id, user_id
- **snapshots**: id, watch_id, fetch_id, content_hash, text (normalised), raw_text (before normalisation, for display), crop_path (nullable), thumbnail_path, created_at, change_summary, ai_summary, added_lines, removed_lines, change_score, keyword_hit (nullable), is_baseline (bool)
- **alerts**: id, watch_id, snapshot_id (nullable for status alerts), kind (`change`|`status`|`flapping`|`threshold`), channel (`email`|`telegram`|`discord`|`digest`), dedupe_key (**UNIQUE**), status (`sent`|`failed`|`queued_digest`), attempts, sent_at, error
- **number_points**: id, watch_id, value, raw, recorded_at
- **check_log**: id, target_id, watch_id (nullable), started_at, finished_at, outcome (`changed`|`unchanged`|`ignored_minor`|`ignored_volatile`|`not_modified`|`error`|`blocked`|`timeout`|`robots_disallowed`), attempt, detail, duration_ms — keep the last ~500 per target
- **templates**: id, token (unique), owner_user_id, config (JSON: url, name, selectors, ignore rules, keywords, sensitivity), created_at

Files live under `DATA_DIR` (`/data` in production): `fetches/{target_id}/{fetch_id}.png|.html.gz`, `crops/`, `thumbs/`, `diffs/`.

---

## 6. API contract (backend ⇄ frontend)

All JSON, all under `/api` except where noted. Auth via an HttpOnly signed cookie `cw_session` (SameSite=Lax, Secure in production, 30 days). Unsafe methods (POST/PUT/PATCH/DELETE) must have an `Origin` header matching `BASE_URL` or `CORS_ORIGINS` (CSRF protection). Errors: `{ "error": { "code": "interval_out_of_range", "message": "Choose an interval between 15 minutes and 24 hours." } }` with a proper HTTP status.

**Auth**
- `POST /api/auth/signup` {email, password, display_name} → user (sets cookie)
- `POST /api/auth/login` {email, password} → user (rate-limited: 10 attempts/min per IP)
- `POST /api/auth/logout`
- `GET /api/auth/me` → user or 401

**URL preview** (public, rate-limited) — used by the landing page and Add page for live validation and the live dial
- `POST /api/url/preview` {url} → {valid, normalised_url, domain, dial_seed, error?}

**Watches**
- `GET /api/watches?status=&q=` → WatchSummary[]
- `POST /api/watches` {url, name?, interval_minutes, sensitivity?, keywords?, keyword_mode?, alert_*?} → WatchDetail (also enqueues an immediate priority check)
- `GET /api/watches/{id}` → WatchDetail
- `PATCH /api/watches/{id}` (name, interval, sensitivity, keywords, number settings, alerts, paused, ignore_carousels)
- `DELETE /api/watches/{id}` (deletes the Target too if no watches remain)
- `POST /api/watches/{id}/check` → 202 {queued: true} or 429 {retry_after_seconds} (2-minute cooldown per target)
- `GET /api/watches/{id}/snapshots?limit=30&before=` → SnapshotItem[] (the timeline)
- `GET /api/snapshots/{id}` → SnapshotDetail (raw_text, screenshot URLs)
- `GET /api/watches/{id}/compare?a={snapshot_id}&b={snapshot_id}` → CompareResult
- `GET /api/watches/{id}/checks?limit=50` → check log entries for this watch's target
- `GET /api/watches/{id}/numbers` → {points:[{t, value, raw}], min, max, latest, change_pct}
- `POST /api/watches/{id}/picker/session` → {frame_url} (signed 10-minute token in the URL)
- `GET /api/watches/{id}/picker/frame?token=` → sanitised HTML (text/html), see R5
- `POST /api/watches/{id}/picker/test` {watch_selectors, ignore_selectors, number_selector} → {text_preview, number_preview, missing_selectors}
- `PUT /api/watches/{id}/selectors` {watch_selectors, ignore_selectors, number_selector} → saves and re-baselines
- `DELETE /api/watches/{id}/volatile-rules/{index}`
- `POST /api/watches/{id}/rss/regenerate` → {rss_url}
- `POST /api/watches/{id}/share` → {template_url}
- `GET /api/templates/{token}` → template preview; `POST /api/templates/{token}/import` → new WatchDetail

**Settings, stats, events, media**
- `GET /api/settings`, `PUT /api/settings`, `POST /api/settings/test-alert` {channel}
- `GET /api/activity?limit=&before=` → feed of changes/errors/blocks across the user's watches
- `GET /api/stats/overview` → {total, changed_today, needs_attention, paused, running, waiting}
- `GET /api/admin/stats` (admin only) → sharing ratio, checks in 24h, outcome rates, avg render ms, queue, per-domain next-allowed times, learned rule counts
- `GET /api/events` → SSE stream (Section 7.9)
- `GET /api/media/fetch/{fetch_id}/screenshot.png`, `/api/media/snapshot/{id}/crop.png`, `/api/media/snapshot/{id}/thumb.jpg`, `/api/media/diff/{a}/{b}.png` — only if the user has a watch on that target

**Public (no login)**
- `GET /rss/{rss_token}.xml`, `GET /healthz`, `GET /bot`, `GET /demo/changing-page`

**Key shapes** (define as Pydantic models; mirror in TS):
- `WatchSummary`: id, name, url, domain, dial_seed, status, status_message, paused, interval_minutes, last_checked_at, last_changed_at, next_due_at, versions, shared_watchers, is_running, number_latest, number_spark (last 20 values), flapping_until
- `WatchDetail`: WatchSummary + watch_selectors, ignore_selectors, ignore_carousels, sensitivity, keywords, keyword_mode, number_selector, number_regex, number_thresholds, alert flags, rss_url, volatile_rules, recent_outcomes
- `SnapshotItem`: id, created_at, summary, ai_summary, added_lines, removed_lines, change_score, thumbnail_url, keyword_hit, is_baseline
- `CompareResult`:
  ```json
  {
    "a": {"id": 4, "created_at": "...", "summary": "..."},
    "b": {"id": 9, "created_at": "...", "summary": "..."},
    "text": {
      "ops": [
        {"type": "equal", "lines": ["..."]},
        {"type": "replace", "pairs": [{"old": [["equal","Price: "],["delete","₹79,900"]],
                                       "new": [["equal","Price: "],["insert","₹74,900"]]}]},
        {"type": "insert", "lines": ["..."]},
        {"type": "delete", "lines": ["..."]}
      ],
      "stats": {"added": 3, "removed": 1, "changed": 1, "change_score": 0.042}
    },
    "visual": {
      "before_url": "...", "after_url": "...", "width": 1366, "height_before": 4200, "height_after": 4310,
      "regions": [{"x": 120, "y": 880, "w": 640, "h": 96}],
      "changed_percent": 4.2, "shifted_by_px": 110, "diff_image_url": "..."
    }
  }
  ```

---

## 7. Backend — core requirements

### R1. Add URL, name, interval; render in a headless browser
- Validate `15 ≤ interval_minutes ≤ 1440` on the server (not just in the form).
- `urlnorm.py`: accept only http/https (add `https://` if missing); lowercase scheme and host; drop default ports, fragments and tracking params (`utm_*`, `fbclid`, `gclid`, `ref`); sort query params; strip trailing slash except root. `dial_seed` = first 8 hex chars of SHA-256 of the normalised URL.
- **Public pages only** (`security.py`): resolve the host and reject private, loopback, link-local, multicast and reserved IPs (`ipaddress` module), and `localhost`. Re-check on every fetch (DNS can change). **Also block private IPs for every sub-request the browser makes** (a public page could embed `<img src="http://169.254.169.254/...">`): in Playwright `context.route("**/*")`, resolve the host (cache 5 min) and abort private destinations.
- **No stored credentials:** reject URLs containing `user:pass@`. Never store cookies; each check uses a fresh browser context.
- Creating a watch: find-or-create the Target, then enqueue a priority check so the first snapshot appears within seconds. If `name` is empty, use the page `<title>` after the first fetch.
- `fetcher.py`:
  - One shared Chromium browser started at app startup, relaunched automatically if it crashes; closed on shutdown.
  - Per check: new `BrowserContext` (viewport 1366×900, honest user agent `ChangeWatchBot/1.0 (+{BASE_URL}/bot)`), no stored state.
  - Block media, fonts and a list of ad/analytics hosts (doubleclick.net, googlesyndication.com, google-analytics.com, googletagmanager.com, facebook.net, adservice.google.com, taboola.com, outbrain.com, hotjar.com, …) via `context.route` — faster, and fewer ads in screenshots.
  - `page.goto(url, wait_until="domcontentloaded", timeout=30s)`, then try `wait_for_load_state("networkidle", timeout=8s)` (ignore its timeout), then settle 1 s.
  - Inject CSS to freeze animations before the screenshot: `*{animation:none!important;transition:none!important;caret-color:transparent!important}`.
  - Collect: final URL, main response status + headers, `page.content()`, title, full-page PNG screenshot (cap height at ~8000 px), and bounding boxes for every selector any watch on this target needs (for crops and picker previews).
  - Whole render wrapped in `asyncio.wait_for(..., 45)`. Global concurrency capped by `asyncio.Semaphore(MAX_BROWSER_PAGES)` (default 3).

### R2. Scheduler + job queue with timeouts and retries
- `scheduler.py`: ticks every 20 s, selects Targets with `next_fetch_at <= now` that have at least one un-paused watch, and enqueues them. Never enqueues a Target already queued or running (in-memory set + `running_since` column).
- `next_fetch_at` gets **±10% jitter** so targets don't all fire at once.
- `jobqueue.py`: `asyncio.PriorityQueue` (0 = user-triggered/first check, 1 = scheduled), `WORKER_COUNT` workers (default 3).
  - Per attempt timeout 45 s; up to 3 attempts; backoff 5 s, 20 s, 60 s with jitter. Retry only retryable failures (timeouts, network errors, 5xx, browser crash). Don't retry 4xx except 429 (honour `Retry-After`).
  - After the final failure: Target `status='error'`, increment `consecutive_failures`, store `last_error`, and schedule the next attempt with **failure backoff** `interval × min(2^consecutive_failures, 8)`.
  - Log every attempt to `check_log`; publish SSE events (7.9).
- Manual "Check now": priority 0, respects the per-domain limiter and a 2-minute per-target cooldown; if the target is already queued or running, attach to that job instead of creating another.
- On startup, reset targets stuck "running" for more than 5 minutes.

### R3. Save text + screenshot; new snapshot only when the content hash changes
For each due Watch on a fetched Target:
1. `extract.py`: parse with BeautifulSoup; remove `script, style, noscript, iframe, svg, canvas, video, audio`, comments, hidden elements (`[hidden]`, `[aria-hidden="true"]`, inline `display:none`), the global noise selectors (8.2) and the watch's `ignore_selectors`. If `watch_selectors` is set, keep only matching elements (document order, blank line between blocks); otherwise the whole `body`. Keep `img[alt]` text.
2. Clean text: block elements → newlines, collapse whitespace, trim, drop empty lines.
3. `noise.py` normalises it (Section 8) → hash with SHA-256.
4. Same hash as `last_content_hash` → no snapshot; update `last_checked_at`, status OK.
5. Different → significance checks (Section 8). Not significant → log `ignored_minor`/`ignored_volatile`, no snapshot, no alert. Significant → create a snapshot (+ crop of the watched region from the element boxes, + a 480 px-wide JPEG thumbnail).
- Save the fetch's screenshot and gzipped HTML **only if at least one watch created a snapshot** (or it's the first fetch). A cleanup task deletes unreferenced fetch files older than 7 days.
- If a watch selector matches nothing: watch `status='error'`, message "The region you picked wasn't found — the page layout may have changed", one deduped alert. Don't report the whole page as changed.

### R4. Noise filtering + sensitivity → Section 8.

### R5. Visual picker (backend side)
- `POST /picker/session` returns a frame URL with a signed 10-minute token (works regardless of cookie rules in iframes).
- `GET /picker/frame` serves the **stored snapshot HTML** (not the live site), sanitised:
  - remove every `<script>` (including inside SVG), all `on*` attributes, `<meta http-equiv="refresh">`, `<object>`, `<embed>`, `<iframe>`, `<frame>`; neutralise `javascript:` URLs; disable forms;
  - add `<base href="{target.url}">` so the site's CSS and images load;
  - inject the picker script **inline with a CSP nonce** and the picker CSS;
  - response header `Content-Security-Policy: default-src 'none'; script-src 'nonce-{nonce}'; style-src * 'unsafe-inline'; img-src * data: blob:; font-src * data:; connect-src 'none'; frame-src 'none'; form-action 'none'; base-uri *`.
- The frontend embeds it in `<iframe sandbox="allow-scripts">` (**no** `allow-same-origin`), so even a hostile page can't touch our cookies or DOM. Communication is `postMessage` only (protocol in 14.7).
- `picker.js` selector algorithm (prefer stable over short): a unique `id` that doesn't look random (reject long digit runs and hash-like ids) → `#id`; else a unique stable attribute (`data-testid`, `data-test`, `itemprop`, `aria-label`, `name`); else build a path upward with `tag.class` using only stable-looking classes (reject `css-1x2y3z`, `sc-…`, long random strings), adding `:nth-of-type(n)` only when needed, stopping when `document.querySelectorAll(sel).length === 1`; max depth 6.
- `PUT /selectors` saves and **re-baselines**: compute the new hash from the latest fetch and store a snapshot marked `is_baseline` — no alert.

### R6. Text diff, screenshot diff, side-by-side, any two versions
- `differ.py`: line diff with `difflib.SequenceMatcher`, then word-level diff inside each replaced line pair; returns the structured `ops` in Section 6 (the frontend renders them). Stats: added, removed, changed, change_score = changed chars ÷ total chars.
- `visual_diff.py` (Pillow): pad both screenshots to the same size; **shift detection** first — on downscaled grayscale copies, find the first differing row, then try vertical offsets −600…+600 px (8 px steps) for the area below it and pick the offset with the smallest difference, so one inserted paragraph doesn't mark the whole rest of the page as changed; report `shifted_by_px`. Then `ImageChops.difference` → grayscale → threshold (>30) → dilate (`MaxFilter(9)`) → 16 px grid of changed cells → flood-fill into rectangles → `regions` + `changed_percent`. Also bake a PNG with translucent red boxes on the new screenshot (used in emails). Cache by `(a, b)`.
- Any two snapshots of a watch can be compared; alerts link to the frontend route `/pages/{id}/compare?a={prev}&b={new}` (absolute, using `BASE_URL`).

### R7. Alerts
- Content: page name, URL, time in the user's timezone, the one-line summary (AI or heuristic), `+X / −Y lines`, up to 5 changed lines (≤200 chars each), and the diff link.
- **Email:** SMTP (`smtplib` via `asyncio.to_thread`) with `SMTP_*` env vars, HTML + plain text. If the host blocks SMTP ports, support `EMAIL_PROVIDER=resend` using Resend's HTTP API (`RESEND_API_KEY`). Not configured → mark `failed` with a clear message; never crash.
- **Telegram:** `POST https://api.telegram.org/bot{token}/sendMessage` (`chat_id`, `parse_mode=HTML`, `disable_web_page_preview=true`), HTML-escaped, ≤4096 chars. App-wide `TELEGRAM_BOT_TOKEN` so users only enter their chat id (Settings explains how to get it).
- **Discord:** `POST {webhook_url}` with an embed (title = page name, url = diff link, description = summary + preview, fields for +/− lines, timestamp), ≤4096 chars.
- **No duplicates:** insert the `alerts` row with `dedupe_key = sha256(f"{kind}:{watch_id}:{content_hash}:{channel}")` first; a UNIQUE violation means it was already handled → skip. Send only after the insert succeeds. Safe across retries, restarts and races.
- Each channel: up to 3 tries (2 s, 10 s, 30 s); one channel failing never blocks the others.
- **Daily digest:** in `daily` mode, changes are stored as `queued_digest`; a task every 10 min sends ONE digest per user after their local `digest_hour` (grouped by page, with summaries and links) and marks them sent. Nothing changed → send nothing.
- **Status alerts:** after 3 consecutive error/blocked checks, ONE "We can't reach this page" alert (key `status:{watch_id}:{status}:{date}`), and ONE "Back to normal" on recovery. Clearly labelled as status, not content change.

### R8. Timeline + dashboard (backend side)
`GET /api/watches` and `/api/stats/overview` give the dashboard everything (status, last checked, last changed, next due, versions, shared watchers, running flag). `GET /snapshots` gives the version timeline; `GET /checks` gives the activity log. The UI is in Section 14.

### 7.9 Live updates (SSE)
`events.py`: an in-process event bus (one `asyncio.Queue` per connected client). `GET /api/events` streams, per user:
- `queue` {running, waiting, workers_busy[]} every 3 s while clients are connected
- `check_started` {watch_ids}, `check_finished` {watch_id, outcome, status, last_checked_at, next_due_at}
- `change` {watch_id, snapshot_id, summary, added, removed}
- `status_change` {watch_id, status, message}
- `ping` every 15 s
Headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`. Users only receive events for their own watches.

---

## 8. Noise handling (requirement 4 + design question 3) — implement every layer

### 8.1 Text normalisation (before hashing)
Compiled regexes in a readable list, each with unit tests:
- Dates/times in many formats (ISO, `15 Oct 2026`, `Oct 15, 2026`, `15/10/2026`, `10:25`, `10:25:52 AM`, weekday names) → `<DATE>`/`<TIME>`
- Relative times (`5 minutes ago`, `2h ago`, `yesterday`, `just now`, `updated 3 days ago`) → `<RELTIME>`
- Countdowns (`13h 33m 52s`, `00:12:45`) → `<TIMER>`
- Engagement counters (`1,234 views`, `12K likes`, `342 online`, `1.2M followers`, `(2,341 reviews)`) → number replaced by `<COUNT>`, word kept — skipped when sensitivity is `high`
- Random tokens: hex ≥16 chars, UUIDs, base64-like ≥24 chars, cache-busters (`?v=123456`), nonces/session ids → `<TOKEN>`
- `© 2025` → `© <YEAR>`; collapse whitespace
Don't normalise prices or plain numbers — users often care about those.

### 8.2 Structural noise removal (before extraction)
Always removed: cookie/consent banners (`[id*="cookie" i], [class*="cookie" i], [id*="consent" i], [class*="consent" i], [class*="gdpr" i]`), ads (`[id^="ad-" i], [class*="advert" i], [class*="ad-slot" i], ins.adsbygoogle, [data-ad], [id*="google_ads"]`), chat widgets (`[id*="intercom"], [class*="crisp"], [id*="hubspot"], [class*="chat-widget" i]`). Rotating banners/carousels (`[class*="carousel" i], [class*="slider" i], [class*="marquee" i], [class*="ticker" i], .swiper, .slick-slider, [role="marquee"]`) are removed when `ignore_carousels` is true (default) — users can turn that off when the carousel is what they want to watch. Show the built-in list (read-only) in the UI.

### 8.3 Volatility learning (the answer to "pages that differ on every load")
- When a watch's hash changes, do a **confirmation re-fetch** ~10 s later (same job, respects rate limits; `CONFIRM_REFETCH=true`).
- Lines that differ between two fetches taken 10 s apart are **volatile** (rotating quotes, random recommendations, A/B tests, tokens the regexes missed). Learn a rule per volatile line — a signature with digits → `#` and long words → `*`, or the CSS path of its element — into `targets.volatile_rules` (cap 50, with `learned_at` and `hits`). Future normalisation drops matching lines.
- Only changes present in **both** fetches vs the baseline and not explained by volatile rules count. Nothing left → log `ignored_volatile` ("page differs on every load — learned N rules").
- Users can see and remove learned rules.
- This doubles requests only when a change is suspected, never on normal checks.

### 8.4 Sensitivity + flapping guard
- **High:** any non-empty diff (counter normalisation off). **Medium** (default): ≥20 changed chars, or a whole added/removed line of ≥5 chars, and change_score ≥ 0.1%. **Low:** ≥100 changed chars and change_score ≥ 2%.
- **Flapping:** ≥4 change alerts in 6 h, or A→B→A→B oscillation (new hash equals the one from two snapshots ago, repeatedly) → raise sensitivity one level for 24 h (`flapping_until`), show a notice in the UI, send at most one "this page is changing a lot" message.

### 8.5 Keyword-only alerts (bonus)
`keywords` (case-insensitive, quoted phrases allowed) + `keyword_mode`: `appear` (keyword newly present), `disappear` (keyword gone, e.g. "Sold out"), `any` (a changed line contains a keyword). Snapshots are still saved so history stays complete; only the alerting is filtered. Store which keyword triggered (`keyword_hit`).

---

## 9. The four design questions — required behaviour

**Q1. Is an outage or CAPTCHA a change? No.** Classify every fetch before diffing:
- `error`: network/DNS failure, timeout, HTTP 5xx, 404/410.
- `blocked`: HTTP 401/403/429, or a bot-wall page — title/body phrases like "Just a moment", "Attention Required", "Verify you are human", "captcha", "Access denied", "unusual traffic", "are you a robot"; elements like `iframe[src*="recaptcha"]`, `iframe[src*="hcaptcha"]`, `#challenge-form`, `[class*="cf-turnstile"]`; or extracted text suddenly below 20% of the last snapshot's length and under 300 chars.
- `error`/`blocked` never create snapshots or change alerts; the last good snapshot stays the baseline, so recovery doesn't trigger a false "everything changed". Never try to solve or bypass CAPTCHAs.

**Q2. Is a URL watched by 200 users fetched 200 times? No — once.** Target/Watch split, URL normalisation, in-flight dedupe, plus a cheap conditional pre-check: before launching the browser, send a HEAD/GET with `If-None-Match`/`If-Modified-Since` (stored `etag`/`last_modified`); on **304** skip the render and log `not_modified`. Show "N people watch this page — fetched once for everyone" in the UI and the sharing ratio on /system.

**Q3. Endless alerts on pages that differ every load?** Normalisation regexes, structural removal, user ignore regions, watching only a picked region, confirmation re-fetch + learned volatility rules, sensitivity thresholds, keyword mode, flapping guard, and content-hash alert dedupe.

**Q4. Hammering a site?** `politeness.py`: at most one request per `DOMAIN_MIN_GAP_SECONDS` (default 10 s) and one concurrent page per registrable domain (`tldextract`); robots.txt fetched and cached 24 h (`urllib.robotparser`), disallowed → watch `blocked` with "Disallowed by robots.txt"; honour `Crawl-delay` (use the larger of it and the default gap); 15-minute minimum interval enforced server-side; 2-minute manual cooldown; `Retry-After` on 429/503; exponential failure backoff; jitter; shared fetching; 304 skips; blocked heavy assets; global page cap; an honest user agent with a `/bot` page explaining the crawler.

---

## 10. Bonus features (backend side)

- **Number tracking:** CSS selector (pickable in the picker's Number mode) and/or regex with one capture group. Parse robustly: `₹1,23,456.50` (Indian grouping), `$1,234.56`, `1.234,56 €` (decide by the last separator), `12K`/`1.2M`, negatives, percentages. Record a point on **every successful check**. Optional thresholds (below X, above Y, change > Z%) alert once per crossing.
- **AI one-line summaries:** if `ANTHROPIC_API_KEY` is set, call `https://api.anthropic.com/v1/messages` with httpx (headers `x-api-key`, `anthropic-version: 2023-06-01`; model from `AI_MODEL`; `max_tokens` ≈ 80; 15 s timeout). Send page name, URL and the diff (`-`/`+` lines, ≤4000 chars); ask for one plain sentence under 20 words, e.g. "Price of the iPhone 16 dropped from ₹79,900 to ₹74,900." Otherwise (or on failure) a **heuristic summary**: "3 lines added, 1 removed. New: 'Registrations close 20 Oct'", choosing the most informative added line. Never call the AI for ignored changes.
- **RSS:** `GET /rss/{token}.xml`, RSS 2.0, latest 30 snapshots: title = summary, link = compare URL, guid = snapshot id + hash, RFC 822 pubDate, description = HTML of added/removed lines, `Content-Type: application/rss+xml`. Regenerate-token endpoint.

---

## 11. Extras for depth

1. **Multi-user:** "N other people watch this page too — fetched once for everyone" on the detail page; "Share setup" creates a template link (`/import/{token}`) that lets another user add the same page with the same regions, ignore rules and keywords (never alert settings).
2. **/system** (admin = first user or `ADMIN_EMAIL`): sharing ratio (watches ÷ targets), checks in the last 24 h, ok/error/blocked rates, average render time, queue, per-domain next-allowed times, learned noise rules.
3. `/healthz` → JSON with DB ok, browser ok, queue size.
4. `/bot` → a plain page describing the crawler, its limits and robots.txt respect.
5. **`/demo/changing-page`** (enabled by `ALLOW_DEMO_PAGE=true`; whitelist only this path on the app's own host past the SSRF guard, e.g. `http://localhost:8000/demo/changing-page` in dev): on every load it shows a fresh timestamp, a random token and a rotating banner (noise), and every 5 minutes its main content really changes. It lets evaluators see noise ignored and real changes caught.
6. **Seed:** `python -m app.seed` creates a demo user and a few watches (the demo page, `https://example.com`, a Wikipedia article, a product page with a price).

---

## 12. Frontend design direction — "haute horlogerie for the web"

**Concept.** ChangeWatch is a watch, so the interface borrows the materials, craft and vocabulary of fine watchmaking: engine-turned **guilloché** dials, **fumé** enamel that darkens toward the edge, **heat-blued steel** hands, **ruby jewels**, **luminous** markers, **Côtes de Genève** stripes on the movement. Every page a user monitors becomes **its own watch dial, engraved with a pattern generated from its URL** — like a serial-numbered timepiece. No other monitoring tool looks like this; that is the identity.

**Spend the boldness in one place: the dials.** Everything around them is quiet and precise, like a fine watch catalogue: generous space, hairline rules, few elements per screen, perfect alignment. Luxury here means restraint, craft and detail — not more effects.

### 12.1 Palette — two rich themes (CSS variables on `:root` and `[data-theme="opaline"]`)

**Fumé** (default, dark) — a green fumé dial with salmon gold and blued steel:
| Token | Hex | Role |
|---|---|---|
| `--fume-center` | `#17392F` | centre of the page's radial background |
| `--fume-edge` | `#060A09` | edge of the background |
| `--surface` | `#0E1714` | panels |
| `--surface-raised` | `#13201C` | menus, modals |
| `--opaline` | `#ECE7DC` | primary text |
| `--rhodium` | `#A9B2AE` | secondary text, rings, ticks |
| `--hairline` | `rgba(236,231,220,.10)` | dividers, borders |
| `--salmon` | `#EFA98C` | primary actions (with `#0B1411` text), guilloché engraving, "changed" highlights |
| `--blued` | `#5B78F6` (hand gradient from `#2440C2`) | hands, links, focus rings |
| `--lume` | `#BFF7D8` (+ soft glow) | OK, live, running, added text |
| `--ruby` | `#F0607F` (jewel `#B3123E`) | errors, removed text |
| `--topaz` | `#F4B860` | blocked, warnings |
| `--moonstone` | `#9FB4C7` | pending |

**Opaline** (light) — a silvered opaline dial with heat-blued steel:
| Token | Hex | Role |
|---|---|---|
| `--bg` | `#E9EAE6` | page (cool silver, not cream) |
| `--surface` | `#F4F4F1` / raised `#FFFFFF` | panels |
| `--ink` | `#141917` / secondary `#4F5754` | text |
| `--hairline` | `rgba(20,25,23,.12)` | dividers |
| `--blued` | `#2340C8` | primary actions (white text), engraving, hands, links |
| `--salmon` | `#C8694A` | "changed" highlights, secondary accent |
| `--lume` | `#1D8A5B` | OK, added |
| `--ruby` | `#B8163F` | errors, removed |
| `--topaz` | `#A86A00` | blocked |
| `--moonstone` | `#5E7A93` | pending |

Status mapping (both themes): OK = lume, error = ruby, blocked = topaz, pending = moonstone, paused = rhodium/secondary text. Status is **never** colour alone — always jewel + word.

### 12.2 Typography
- **Display: Zodiak** (Indian Type Foundry, free on Fontshare) — a high-contrast serif with sharp, engraved-feeling details. Page titles, dial readouts, big numbers, the landing headline. Weights 300–400, never bold.
- **Text/UI: Switzer** (also ITF, Fontshare) — a Swiss-style grotesk; the name is the point ("Swiss made"). Everything else.
- **Mono: JetBrains Mono** — only inside diff views, where alignment matters.
- Load from Fontshare; if the CDN is slow or unavailable, download the woff2 files into `src/assets/fonts/` and self-host. Fallbacks: Zodiak → "Bodoni Moda", Georgia, serif; Switzer → "Hanken Grotesk", system-ui, sans-serif.
- Scale (px): 12, 14, 16, 18, 21, 24, 32, 44, 60, 84. Body 16/1.55 Switzer 400; small 14/1.5; page titles Zodiak 44/1.1 (60 on wide screens); section titles Zodiak 32/1.15; landing headline Zodiak 84/1.0 (44 on mobile); dial readouts Zodiak with lining tabular numerals.
- Sentence case everywhere. Prose max 68 characters per line. `font-variant-numeric: tabular-nums lining-nums` for counts, times and tables.

### 12.3 Materials and texture (pure CSS/SVG, no image assets)
- **Background (Fumé):** radial gradient from `--fume-center` at 50% 0% to `--fume-edge`, plus a fixed grain layer (SVG `feTurbulence`, ~3% opacity) so the gradient never bands.
- **Dial surface:** sunburst brushing with a very fine `repeating-conic-gradient` (alternating rays at 2–4% opacity) under the guilloché, and a soft **specular highlight that follows the pointer** (radial gradient positioned by `--mx/--my` set on pointermove). Only on dials and the landing hero.
- **Movement plate:** Côtes de Genève stripes — `repeating-linear-gradient` at 115° with soft light bands on rhodium grey.
- **Depth:** no generic grey drop shadows. Raised surfaces use a dark tinted shadow plus a 1 px top inner highlight (a polished bevel). Dials sit in a thin case ring with a subtle metallic `conic-gradient`.
- **Radii by hierarchy:** dials are circles; main panels 20 px; inputs 12 px; primary buttons fully rounded (like a crown); chips 8 px.

### 12.4 Motion principles — motion explains state
- **One orchestrated moment per page load.** Dashboard: every dial "winds" — hands sweep from 12 o'clock to their true positions (900 ms, 40 ms stagger) while the guilloché engraves in. Landing: the hero dial engraves itself and its hands set to the current time.
- **Live, meaningful motion:** sweep hands show real progress to the next check; the Movement turns only while checks run; a dial re-engraves once when its page changes.
- **Responsive motion:** buttons press (scale .98) with a single specular sheen sweep on hover; dials tilt toward the pointer (max 6°); the loupe glides on a spring; route changes use a shared-element transition (the clicked dial grows into the detail page).
- **Don't:** fade-and-slide-up on every section, hover-lift on every element, parallax everywhere, bouncing, looping attention-seekers.
- Tokens: `--ease-out: cubic-bezier(.22,1,.36,1)`, `--ease-mech: cubic-bezier(.65,0,.35,1)`; durations 160 ms (hover/press), 280 ms (UI state), 600 ms (routes), 900 ms (orchestrated load). Springs (loupe, tilt): stiffness 300, damping 30.
- **`prefers-reduced-motion: reduce`:** hands jump to position and update every 30 s, engraving appears instantly, no tilt, transitions become ≤120 ms fades. Everything still works.

### 12.5 Writing (UI copy)
Plain words, sentence case, active voice. Luxury comes from the visuals, not jargon — name things as users think of them: "Pages", "Add page", "Activity", "Settings", "Check now", "Compare versions", "Pick regions". Keep one verb through a flow: the "Add page" button produces the toast "Page added. First check running." Errors say what happened and what happens next: "Couldn't reach vit.ac.in — it timed out after 30 seconds. We'll try again at 4:15 PM." Blocked: "vit.ac.in is showing a bot check, so we kept your last good version and will retry later." Empty states invite action: "You're not watching any pages yet. Paste a link to start." No exclamation marks, no emoji, no "Oops".

### 12.6 Avoid — these make a site look generic or AI-made
- Identical rounded cards in a grid, each with the same soft grey shadow.
- ALL-CAPS letter-spaced labels above headings; metadata strings joined with " · "; "→" appended to buttons or links; 01/02/03 numbering on things that aren't a real sequence.
- Cream background with a terracotta accent; black background with one neon accent; glassmorphism blobs; gradient text; purple-blue "AI" gradients; emoji in the UI; stock illustrations; any component-library look.

### 12.7 Quality floor (non-negotiable)
- WCAG AA contrast in both themes; full keyboard navigation; visible focus ring (2 px `--blued` + soft glow); touch targets ≥44 px.
- Responsive down to 360 px, no horizontal page scroll.
- Performance: a dashboard with 30 dials stays smooth. Guilloché paths are computed once per seed/size and cached (in-memory `Map` + `sessionStorage`); off-screen dials use `content-visibility: auto`; animate only `transform`/`opacity`/`stroke-dashoffset`; Lighthouse performance ≥85 on the dashboard.
- **Design review loop:** before building the frontend, write `docs/04-design-system.md` (tokens, type, layout, principles) and check it against this section. After building each screen, use Playwright to screenshot it at 1440×900 and 390×844 in both themes, **look at the screenshots**, and fix anything misaligned, cramped, low-contrast or generic before moving on.

---

## 13. Signature components

### 13.1 The dial (`components/dial/`) — see `docs/design/dial-reference.png`
- Case ring at radius R; hairline inner ring at 0.80R; railway-track chapter ring of 60 minute ticks between 0.84R and 0.93R (every 5th tick longer and thicker).
- Guilloché field generated from the page's `dial_seed` (13.2).
- **Status jewel** at 12 o'clock, 0.62R from centre: a cabochon with a radial gradient and a white specular dot (lume = OK, ruby = error, topaz = blocked, moonstone = pending, rhodium = paused). A glint sweeps across it once on hover.
- **Date window** at 3 o'clock, 0.52R: a small aperture showing time since the last change ("now", "5m", "2h", "3d", "—") in Zodiak numerals, ink on opaline.
- **Sub-counter** at 6 o'clock (large detail dial only, if number tracking is on): latest value with odometer digits.
- **One blued-steel sweep hand** (centre to 0.86R, short counterweight tail) shows progress to the next check: 12 o'clock = just checked, a full turn = next check due. Blued screw-head centre cap.
- While a check runs for this page, the hand holds still and a thin lume arc travels around the chapter ring.
- Sizes: sm 160 px (grid), md 240 px, lg 360–440 px (detail), landing hero up to 560 px.
- SVG. Guilloché `<path>`s with `fill: none`, `vector-effect: non-scaling-stroke`, stroke 0.6 px (sm) to 0.9 px (lg), engraving colour = `--salmon` (Fumé) or `--blued` (Opaline) at the per-line opacity below.
- Accessible: `role="img"` with an `aria-label` like "VIT News: OK. Checked 4 minutes ago, changed 2 hours ago, next check in 11 minutes."

### 13.2 Guilloché generator (`components/dial/guilloche.ts`) — exact algorithm (prototyped and tuned)
A pure function `guillochePaths(seedHex, { radius, detail })` → `{ d: string; opacity: number }[]`, centred at (0, 0).

1. PRNG: `seed = parseInt(seedHex, 16)` into mulberry32:
   ```ts
   export function mulberry32(seed: number) {
     let a = seed >>> 0;
     return () => {
       a = (a + 0x6D2B79F5) >>> 0;
       let t = a;
       t = Math.imul(t ^ (t >>> 15), t | 1);
       t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
       return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
     };
   }
   ```
2. Draw parameters **in this order** (so a seed always gives the same dial):
   - `style` = `['rosette','wave','woven','lattice'][Math.floor(rnd()*4)]`
   - `k` (petals) = integer in [9, 24]
   - `N` (lines) = integer in [36, 60] — for `lattice`, an integer in [24, 32] per family; for `sm` dials multiply N by 0.6
   - `A` = (0.035 + rnd()·0.045)·R
   - `m` = rnd() < 0.5 ? 2 : 3
   - `A2` = A·(0.15 + rnd()·0.30)
   - `turns` = 0.5 + rnd()·1.5
3. For each line i = 0…N−1, with t = i/N:
   - rosette: base = R(0.12 + 0.62t), φ = 2π·t·turns
   - wave: base = R(0.10 + 0.64t), φ = 1.2·sin(2π·t·turns)
   - woven: base = R(0.40 + 0.18t), φ = 2π·t·turns, amplitude A × 2.6
   - lattice: two families with s = +1 and s = −1: base = R(0.12 + 0.62t), φ = s·2π·t·turns
   - **r(θ) = base + A·sin(kθ + φ) + A2·sin(k·m·θ − φ/2)**, sampled θ = 0…2π with 900 (lg), 480 (md) or 300 (sm) steps; path from `M`/`L` commands (2 decimals), closed with `Z`.
   - opacity = 0.35 + 0.45·(0.5 + 0.5·sin(π·t))
4. **Engrave animation** (md/lg, motion allowed): give each path `pathLength="1"`, `stroke-dasharray: 1`, animate `stroke-dashoffset` 1 → 0 over 1200 ms ease-out with an 8 ms stagger, inner lines first.
5. **Re-engrave on change:** the same animation once, plus one soft salmon halo pulse on the case (1.2 s).
6. **Live preview** (landing and Add page): as the user types, call `/api/url/preview` (debounced 250 ms) and cross-fade to the new pattern (300 ms) — don't re-engrave on every keystroke.
7. Memoise by `${seed}:${size}:${detail}:${theme}`.

### 13.3 Sweep hand — CSS, not JavaScript per frame
```css
.hand { animation: sweep var(--period) linear infinite;
        animation-delay: calc(var(--elapsed) * -1); }
@keyframes sweep { from { transform: rotate(0turn) } to { transform: rotate(1turn) } }
```
Set `--period` = interval in seconds and `--elapsed` = seconds since the last check (both with an `s` unit, as inline styles). Re-sync when new data or an SSE event arrives. Paused watch: `animation-play-state: paused` and a slightly desaturated dial. Make sure the rotation origin is exactly the dial centre — verify visually.

### 13.4 The Movement (live view of the scheduler)
An SVG gear train on a Côtes de Genève plate, top-right of the dashboard (~240×160), larger on /system.
- Three gears, an escape wheel and a balance wheel. Teeth for n teeth and module m: pitch radius rp = m·n/2, tip radius ra = rp + m, root radius rf = rp − 1.25m; each tooth a trapezoid (root half-width 0.25p, tip half-width 0.12p, with p = 2π/n).
- Meshing: centre distance = m(n1 + n2)/2; ω2 = −ω1·n1/n2; to interlock, gear 1 starts at phase α and gear 2 at α + π − π/n2, where α is the angle from gear 1's centre to gear 2's.
- Colours: rhodium plates, salmon-gold gears (brass in Opaline), ruby jewels at the pivots.
- Driven by SSE `queue` events: idle → balance wheel swings slowly (3 s), gears still; checks running → gears turn (speed grows with running checks) and the balance swings at 1 s; one jewel per worker glows lume while busy. Label in plain words: "2 checks running, 5 waiting". Click → /system.
- It makes the queue, the workers and the politeness limits visible — use it in the demo.

### 13.5 The Loupe (Compare → Screenshot)
- A 220 px circular magnifier follows the pointer over the screenshot: steel bezel with a knurled edge (`repeating-conic-gradient`), 2.5× zoom (Alt/Option + scroll changes 1.5×–4×), soft lens vignette.
- A div whose `background-image` is the newer screenshot, `background-size` = displayed size × zoom, `background-position` from the pointer. Changed regions (from the API, in screenshot pixels) are drawn as ruby-glow rectangles on the image and, scaled, inside the lens.
- **Hold Space** (or press-and-hold on touch) to show the **older** version inside the lens only — like lifting the crystal to see what was there before. Hint under the image: "Hold Space to see the older version under the loupe."
- Spring-follow with Motion's `useSpring`; hidden when the pointer leaves; on touch it appears where you touch and can be dragged.

### 13.6 Odometer numbers
Live-updating numbers (dashboard summary, tracked values, date windows) roll digit by digit like a date wheel: each digit is a vertical 0–9 strip moved with a spring; tabular figures so nothing shifts. Instant swap with reduced motion.

### 13.7 Sound (optional, off by default)
A small speaker toggle in the top bar. When on: a soft mechanical tick when a check finishes, and a two-note chime (like a minute repeater, e.g. 1318 Hz then 988 Hz with exponential decay) when a change is detected. Synthesised with Web Audio — no audio files. Create the AudioContext on the first click of the toggle (browser autoplay rules).

### 13.8 Shared-element transitions
Grid dials use Motion `layoutId={"dial-" + id}`; the detail page's large dial uses the same id, so clicking a dial grows it into the detail page (600 ms ease-out) and Back reverses it. Other content cross-fades (200 ms).

---

## 14. Frontend pages, layouts and behaviour

### 14.1 Routes
| Route | Page |
|---|---|
| `/` | Landing (logged out) or Dashboard (logged in) |
| `/login`, `/signup` | Auth |
| `/pages/new` | Add page |
| `/pages/:id` | Page detail (tabs: History, Numbers, Activity, Settings) |
| `/pages/:id/compare?a=&b=` | Compare versions (alert links land here) |
| `/pages/:id/picker` | Pick regions |
| `/activity` | Changes, errors and blocks across all pages |
| `/settings` | Alerts, digest, timezone, theme, sound |
| `/system` | Admin view of the engine |
| `/import/:token` | Add a page from a shared setup |

### 14.2 Landing (logged out)
```
┌──────────────────────────────────────────────────────────────────────┐
│ (dial mark) ChangeWatch                              Log in   Sign up │
│                                                                      │
│                       ╭──────────────────╮                           │
│                     ╱   large guilloché   ╲    engraves on load;     │
│                    │    dial, hands show   │   hands show the        │
│                    │    the current time   │   current time; the     │
│                     ╲                     ╱    pattern morphs as     │
│                       ╰──────────────────╯     you type a URL        │
│                   Nothing changes unnoticed.                         │
│     ChangeWatch watches the pages you care about, ignores the        │
│     noise, and tells you the moment something real changes.          │
│      [ Paste a page you want to watch            ] [ Start watching ]│
│      Every page gets its own dial, engraved from its address.        │
├──────────────────────────────────────────────────────────────────────┤
│ Scroll scene (the one scroll-linked animation): the dial tilts back  │
│ (CSS 3D, rotateX ≈ 55°) and separates into four layers, each         │
│ labelled with a step of the pipeline — a real sequence:              │
│   1 Render: a real browser opens the page and takes a screenshot     │
│   2 Filter: timestamps, ads, counters and random tokens are removed  │
│   3 Compare: text and screenshot differences, any two versions       │
│   4 Alert: email, Telegram or Discord, once per real change          │
├──────────────────────────────────────────────────────────────────────┤
│ The hard questions, answered — four short Q&As in two columns        │
├──────────────────────────────────────────────────────────────────────┤
│ Footer: wordmark, "Made by Kushagra Singhal", GitHub link            │
└──────────────────────────────────────────────────────────────────────┘
```
"Start watching" goes to signup with the URL carried through, then straight to Add page prefilled. Lenis smooth scroll on this page only. Use Motion `useScroll`/`useTransform` for the scroll scene.

### 14.3 Dashboard
```
┌──────────────────────────────────────────────────────────────────────┐
│ (mark) ChangeWatch   Pages  Activity  Settings      ♪  ◐  [Add page] K│
├──────────────────────────────────────────────────────────────────────┤
│ Good evening, Kush                                  ┌──────────────┐ │
│ 3 of your 12 pages changed today. 1 needs attention.│  Movement    │ │
│                                                     └──────────────┘ │
│ [All 12] [Changed today 3] [Needs attention 1] [Paused]  search  Dials | List │
│                                                                      │
│    ◯           ◯           ◯           ◯           ◯                 │
│  VIT News    Wikipedia   Amazon      GitHub      Example             │
│  vit.ac.in   wikipedia…  amazon.in   github.com  example.com         │
│              Blocked by a bot check                                  │
└──────────────────────────────────────────────────────────────────────┘
```
- A plain-language summary sentence instead of stat tiles. Left-aligned content.
- **Dials view** (default): responsive grid of sm dials with the page name (Zodiak 21) and domain (Switzer 14, secondary) below; a status line appears only when the page isn't OK. Hover: tilt + specular light; a small action menu (Check now, Pause, Edit, Delete). Click: shared-element transition into detail.
- **List view**: a clean table — Page, Status, Last checked, Last changed, Next check, Interval, Versions, Shared — sortable, with the same actions. On mobile it becomes stacked rows.
- Live via SSE; on a `change` event: that dial re-engraves, the summary sentence's numbers roll, and a toast shows "VIT News changed: Registration deadline moved to 20 Oct" with a "Compare" action.
- Empty state: a faint large dial with the URL field inside the page — "You're not watching any pages yet. Paste a link to start."

### 14.4 Add page
Two columns: the form on the left (URL with live validation via `/api/url/preview`, name, interval as a segmented control `15m 30m 1h 3h 6h 12h 24h Custom`, sensitivity Low/Medium/High with one-line explanations, a "More options" disclosure for keywords and alerts), and the **live dial preview** on the right that changes as the URL is typed. Submit "Add page" → navigate to the detail page while the first check runs (the dial shows the running arc). *Optional polish if time allows:* the interval as a rotating bezel control (drag or arrow keys, with detents), keeping the segmented control for accessibility.

### 14.5 Page detail
```
┌──────────────────────────────────────────────────────────────────────┐
│ All pages                                                            │
│  ┌──────────────┐   VIT News                                         │
│  │  large dial  │   vit.ac.in/news (opens in a new tab)              │
│  │  (440 px)    │   Checked 4 minutes ago. Changed 2 hours ago.      │
│  │              │   Next check in 11 minutes, every hour.            │
│  └──────────────┘   2 other people watch this page too, so it's      │
│                     fetched once for everyone.                       │
│                     [Check now] [Pick regions] [Compare versions] […]│
│  History   Numbers   Activity   Settings                             │
│  Today 2:14 PM      Registration deadline moved to 20 Oct.  +3 −1  [thumb] Compare with previous │
│  Yesterday 9:02 AM  …                                                │
└──────────────────────────────────────────────────────────────────────┘
```
- **History:** a vertical timeline on a blued-steel hairline; each version marker is a tiny blued screw head (the newest has a lume dot). Time on the left, summary (AI if present, with a small sparkle icon), `+X −Y`, thumbnail, "Compare with previous", and a checkbox on every row so any two can be compared ("Compare selected"). Baselines are labelled "New starting point (regions changed)". Keyword hits say which keyword triggered.
- **Numbers:** Recharts line chart styled to the theme (hairline grid, lume line, salmon dots where the page changed), min/max/latest and change since first; threshold settings.
- **Activity:** the check log in plain words ("Unchanged", "Ignored a tiny change", "Ignored: this part changes on every load", "Couldn't reach the site", "Bot check shown", "Disallowed by robots.txt").
- **Settings:** name, interval, sensitivity, keywords + mode, number selector/regex, alert channels, ignore carousels, learned noise rules (each removable), built-in noise filters (read-only), RSS link (copy, regenerate), "Share setup" link, Pause, Delete.
- A notice when `flapping_until` is set: "This page is changing a lot, so we've raised its sensitivity until tomorrow."

### 14.6 Compare
```
┌──────────────────────────────────────────────────────────────────────┐
│ VIT News   Compare [14 Oct, 9:02 AM ▾]  with  [15 Oct, 2:14 PM ▾]    │
│ Registration deadline moved to 20 Oct. 3 lines added, 1 removed.     │
│ 4.2% of the page looks different.                                    │
│ [Text] [Side by side] [Screenshot] [Slider] [Overlay]                │
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │ selected view                                                     │ │
│ └──────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```
- **Text:** unified diff — added lines on a lume tint, removed on a ruby tint with strikethrough, word-level highlights inside changed lines, unchanged runs collapsed ("Show 23 unchanged lines").
- **Side by side:** two aligned columns with the same highlights and collapsing.
- **Screenshot:** the newer screenshot with ruby-glow regions + the Loupe (13.5). If `shifted_by_px` isn't 0, a note: "Content moved down 110 px; we lined the versions up before comparing."
- **Slider:** old and new stacked with a draggable divider (`clip-path`), synchronised scrolling.
- **Overlay:** onion skin with an opacity slider.
- Both version pickers list every snapshot; the URL updates so the view is shareable.

### 14.7 Pick regions
```
┌──────────────────────────────────────────────────────────────────────┐
│ VIT News   Pick regions   [Watch] [Ignore] [Number]           [Save] │
│ ┌──────────────────────────────────────┐ ┌─────────────────────────┐ │
│ │ page snapshot in a sandboxed iframe   │ │ Watching                │ │
│ │ hover outline + selector tooltip      │ │  #news-list        ✕    │ │
│ │                                       │ │ Ignoring                │ │
│ │                                       │ │  .ticker           ✕    │ │
│ │                                       │ │ Number                  │ │
│ │                                       │ │  .price  (₹74,900)      │ │
│ │                                       │ │ [Test selection]        │ │
│ │                                       │ │ preview of the text…    │ │
│ └──────────────────────────────────────┘ └─────────────────────────┘ │
│ ↑ selects the parent element. Esc cancels.                           │
└──────────────────────────────────────────────────────────────────────┘
```
- Mode colours: Watch = lume, Ignore = ruby, Number = blued. Picked regions keep persistent overlays. Selectors are also editable as text for power users.
- iframe `src` comes from `POST /picker/session`; `sandbox="allow-scripts"` only.
- postMessage protocol — parent → frame: `{type:'mode', mode}`, `{type:'highlight', selectors:{watch, ignore, number}}`; frame → parent: `{type:'ready'}`, `{type:'hover', selector}`, `{type:'pick', selector, textPreview}`. The parent accepts messages only when `event.source === iframe.contentWindow`.
- "Save" calls `PUT /selectors`; toast "Regions saved. Future checks only look at what you picked."

### 14.8 Activity, Settings, System, Import
- **Activity:** one feed of changes, errors and blocks across all pages, newest first, filter by page and type.
- **Settings:** sections separated by hairlines (not cards): Profile and timezone; Alerts — Email, Telegram (chat id + how to get it), Discord (webhook URL), each with a status ("Connected" / "Not set up") and "Send test"; Daily digest (on/off + hour); Appearance (Fumé / Opaline, sound).
- **System:** the large Movement plus the admin stats in Section 11.2, explained in plain sentences.
- **Import:** shows the shared setup (page, regions, keywords) and "Add this page".

### 14.9 Data layer
- `api/client.ts`: fetch wrapper with `credentials: 'include'`, JSON parsing, typed `ApiError` (status, code, message); 401 → redirect to `/login`.
- TanStack Query hooks per endpoint; optimistic updates for pause/resume; skeleton loaders that look like brushed metal shimmer (not grey boxes).
- `realtime/useEvents.ts`: one `EventSource('/api/events')` after login; on events, invalidate the right queries, drive the Movement, trigger re-engraves, toasts and sounds; reconnect with backoff; fall back to polling every 30 s if SSE fails.
- Times: relative ("4 minutes ago") with the exact time in the user's timezone on hover.

---

## 15. Teach me the code (mandatory)

### 15.1 In the code
- Every file starts with a short header comment: what it does, who uses it, what it depends on.
- Every function, class and React component has a plain-English docstring/JSDoc: what it does, inputs, outputs, and **why it exists**.
- Comment the *why* of anything non-obvious (why a lock, why jitter, why a nonce, why `pathLength="1"`).
- Simple, readable code: descriptive names, type hints in Python, strict TypeScript, no clever one-liners, no unnecessary abstractions.

### 15.2 After every phase, tell me in chat (and append to `docs/BUILD-LOG.md`)
1. **What I built** — 2–4 sentences, no jargon.
2. **How it works** — the flow as numbered steps.
3. **Files created or changed** — one line each.
4. **How to try it yourself** — exact commands and clicks.
5. **Words to know** — 2–5 terms with one-line definitions.
6. **A question an evaluator might ask about this, and a good answer.**

### 15.3 Final documentation in `docs/`
- `01-big-picture.md` — the system in one page with a Mermaid diagram, then **"what happens when you click Add page"** traced step by step through frontend → API → DB → queue → worker → politeness → Playwright → classification → extraction → noise → hash → snapshot → alerts → SSE → the dial updating.
- `02-backend-tour.md` — every backend file: purpose, key functions, how it connects.
- `03-frontend-tour.md` — every frontend file: purpose, how data flows from the API to the screen, how each signature animation works (with the maths for the guilloché and gears in simple words).
- `04-design-system.md` — the horology concept, palette, fonts, motion rules, and why each choice was made.
- `05-concepts.md` — a glossary explained like I'm a first-year student, each with "where it's used in our code": HTTP, REST, JSON, cookies and sessions, password hashing, SQL and indexes, hashing (SHA-256), headless browser, async/await and the event loop, job queue and workers, scheduler, timeouts, retries, exponential backoff, jitter, rate limiting, robots.txt, ETag/304, SSRF, CSP and nonces, iframe sandbox and postMessage, CSRF, SSE, CORS, React components/state/hooks, TanStack Query, SPA routing, CSS variables, SVG, the diff algorithm (SequenceMatcher / longest matching blocks), idempotency and dedupe keys, Docker, environment variables.
- `06-questions-and-answers.md` — **at least 50** likely evaluator questions with short, confident answers, grouped: architecture, scheduling and queue, scraping ethics and politeness, noise and diffing, alerts, security, database, frontend and design, testing, deployment, scaling ("How would you handle a million pages?"), trade-offs ("Why SQLite?", "Why one Uvicorn worker?", "Why Playwright instead of requests?", "What happens if the server restarts mid-check?", "How does the picker build a selector?", "What's the time complexity of your diff?"). Include "Did you use AI to build this?" with an honest answer: I designed the approach, built it with an AI coding assistant (Claude Code), and studied every part — then point to the docs as proof.
- `07-demo-script.md` — a 4-minute demo walkthrough: what to click and what to say, showing every core requirement, the four design questions (using `/demo/changing-page` and /system), and the bonuses.

### 15.4 At the very end
Give me a 15-minute guided tour of the codebase in chat, then **quiz me with 10 questions one at a time**, correcting my answers.

### 15.5 `CLAUDE.md` (create first)
Include: one-paragraph project summary; folder map; how to run backend, frontend and tests; code conventions; the design rules from Section 12 in brief; and these standing rules:
- After any change, explain what changed and why in simple language.
- When I ask "explain X", explain it like I'm a first-year CS student: start with a real-world analogy, then the actual mechanism, then point to the exact file, function and line numbers.
- Keep `docs/` up to date whenever behaviour changes.

---

## 16. Configuration

`backend/.env.example`:
```
BASE_URL=http://localhost:5173
SECRET_KEY=change-me-long-random-string
DATA_DIR=./data
FRONTEND_DIST=                     # set in Docker to the built frontend folder
CORS_ORIGINS=                      # only for split hosting
WORKER_COUNT=3
MAX_BROWSER_PAGES=3
DOMAIN_MIN_GAP_SECONDS=10
CONFIRM_REFETCH=true
ALLOW_DEMO_PAGE=true
ADMIN_EMAIL=
DEBUG_FAST_SCHEDULE=false          # testing only: treat minutes as seconds

EMAIL_PROVIDER=smtp                # smtp | resend
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=                     # Gmail App Password
SMTP_FROM=ChangeWatch <you@gmail.com>
RESEND_API_KEY=

TELEGRAM_BOT_TOKEN=                # optional app-wide bot

ANTHROPIC_API_KEY=                 # optional AI summaries
AI_MODEL=claude-haiku-5-5
```
`frontend/.env.example`: `VITE_API_BASE=` (empty = same origin).

Everything must work with only `BASE_URL` and `SECRET_KEY` set; email/Telegram/Discord/AI show "Not set up" in the UI instead of failing.

---

## 17. Build phases and time plan (IST, 15 Oct)

Times are targets. If you fall more than 45 minutes behind, cut in this order: bezel control → sound → landing scroll scene → overlay view → share templates. Never cut a core requirement or the deploy.

| # | Phase | Target |
|---|---|---|
| 0 | Scaffold: folders, CLAUDE.md, git, backend hello on 8000, Vite app on 5173, proxy working (`/api/health` visible from the frontend), `dev.sh`, `playwright install chromium` | 11:30 AM |
| 1 | Design system (`04-design-system.md` first, then tokens, fonts, both themes, textures, base UI components, TopBar) + backend auth + Login/Signup screens | 12:30 PM |
| 2 | URL normalisation + SSRF guard, Targets/Watches, fetcher, extraction, first snapshot; Add page; Dashboard with the **Dial** (guilloché, jewel, date window, sweep hand) and List view | 1:45 PM |
| 3 | Scheduler, job queue, retries, politeness, robots.txt, classification (ok/error/blocked), check log, SSE, live dashboard, **Movement** | 2:45 PM |
| 4 | Noise pipeline, sensitivity, confirmation re-fetch + volatility learning, flapping, keyword mode, `/demo/changing-page`, pytest for every rule | 3:45 PM |
| 5 | Diffs, shift-aware screenshot diff, Compare page (all five views + **Loupe**), History timeline, Activity tab | 5:00 PM |
| 6 | Visual picker (sanitised frame, picker.js, three modes, test + save + re-baseline) | 6:00 PM |
| 7 | Alerts (email/Telegram/Discord, dedupe, retries, status alerts, digest) + Settings page | 6:45 PM |
| 8 | **Deploy v1** to Railway (Section 18) and verify the live URL | 7:30 PM |
| 9 | Bonus: numbers + charts + thresholds, AI summaries, RSS, share templates, shared-watcher messages, /system, seed | 8:45 PM |
| 10 | Landing page + scroll scene, odometer, sound, shared-element transitions, final screenshot review in both themes and on mobile | 9:45 PM |
| 11 | Docs (Section 15.3), README, acceptance checklist, redeploy, guided tour + quiz | 10:45 PM |

Commit after every phase. Use `DEBUG_FAST_SCHEDULE=true` only for local testing of scheduling.

---

## 18. Deployment (single container on Railway)

Root `Dockerfile` (multi-stage):
```dockerfile
# Stage 1: build the frontend
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: backend runtime with Chromium
# The tag must match the playwright version pinned in backend/requirements.txt exactly.
FROM mcr.microsoft.com/playwright/python:v<PLAYWRIGHT_VERSION>-noble
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=web /web/dist ./frontend_dist
ENV DATA_DIR=/data FRONTEND_DIST=/app/frontend_dist PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
```
- **Exactly one Uvicorn worker** — the scheduler, queue and SSE bus live in-process; more workers would duplicate them. Explain this in the docs.
- `railway.json`: Dockerfile builder, healthcheck `/healthz`.
- README steps: create a Railway project from the GitHub repo → add a Volume mounted at `/data` → set env vars (`BASE_URL` = the Railway URL, `SECRET_KEY`, optional email/Telegram/AI) → deploy → open `/healthz`.
- Render alternative: Docker web service + persistent disk at `/data`. Note that free instances that sleep when idle also stop the scheduler.

---

## 19. README.md (evaluators read this first)
1. One-paragraph pitch + screenshots (dashboard dials, compare with loupe, picker, landing) in `docs/screenshots/`.
2. Live demo link + demo login from the seed script.
3. Table: each core requirement → how it's implemented → files.
4. **The four design questions, answered** (Section 9) with file references.
5. Architecture diagram (Mermaid): Scheduler → Job queue → Workers → Politeness → Fetcher → Classifier → per-watch evaluator (extract → normalise → hash → volatility/sensitivity/keywords) → Snapshots → Alerts → SSE → Frontend.
6. How frontend and backend work together (dev proxy, single container in production).
7. Noise pipeline step by step; bonus features; design concept with a dial image.
8. Local setup on macOS: backend (`python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && playwright install chromium && cp .env.example .env && uvicorn app.main:app --reload --port 8000`), frontend (`npm install && npm run dev`), or `./dev.sh`.
9. Deployment; limitations and future work (Redis queue for horizontal scaling, Postgres, S3 for screenshots, browser extension, per-user API keys).

---

## 20. Final acceptance checklist (verify each yourself before saying you're done)
**Engine**
- [ ] Two users add the same URL with different `utm` params → one Target, one fetch per cycle; both see "fetched once for everyone".
- [ ] `localhost`, `127.0.0.1`, `192.168.x.x`, `169.254.169.254` and `http://user:pass@site.com` are rejected; the browser blocks private sub-requests.
- [ ] Interval <15 or >1440 is rejected by the API itself.
- [ ] A new page gets its first snapshot (text + screenshot) within ~30 s.
- [ ] Re-checking an unchanged page creates no snapshot.
- [ ] `/demo/changing-page`: per-load noise is ignored; the real 5-minute change is detected and alerted exactly once.
- [ ] A 503/timeout URL → Error, no snapshot, no change alert; one status alert after 3 failures; no false change on recovery.
- [ ] A CAPTCHA/"Just a moment" page → Blocked, not a change.
- [ ] Picker: watch one region and ignore another; changes outside the watched region don't alert.
- [ ] Unified, side-by-side, screenshot (with loupe), slider and overlay all work for any two versions.
- [ ] Email/Telegram/Discord test alerts work when configured; a change alerts each enabled channel once; re-running a job doesn't duplicate.
- [ ] Daily digest batches changes into one message.
- [ ] Keyword alerts, number chart, AI summary (and fallback without a key), RSS feed all work.
- [ ] Check log shows no two requests to one domain inside the gap; robots.txt disallow is respected.
- [ ] `pytest` passes.

**Frontend and design**
- [ ] Frontend and backend run separately in dev (5173 + 8000) and as one container in production.
- [ ] Each page has its own dial pattern, stable across reloads; sweep hands match real next-check times; jewels match status.
- [ ] Dashboard updates live via SSE (no refresh); the Movement reacts to running checks; a change re-engraves its dial and shows a toast.
- [ ] Landing dial morphs as you type a URL; the scroll scene works; Lenis only on the landing page.
- [ ] Both themes look finished; screenshots reviewed at 1440 px and 390 px; no horizontal scroll on mobile.
- [ ] Keyboard navigation and focus rings work everywhere; `prefers-reduced-motion` is respected.
- [ ] None of the generic patterns in 12.6 appear anywhere.

**Delivery**
- [ ] `docker build .` succeeds and the deployed URL works with a volume at `/data`.
- [ ] No secrets committed; `.env` files are gitignored.
- [ ] All docs in Section 15.3 exist and match the final code.

When everything passes, tell me: what was built, how to run it locally, the live URL and how it was deployed, and anything that still needs my input (API keys, Gmail App Password, Telegram bot). Then start the guided tour and quiz (15.4).
