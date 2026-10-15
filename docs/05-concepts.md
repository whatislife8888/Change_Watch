# Concepts, explained simply

Each entry has the idea in plain words, and then where it's used in our code.

**HTTP.** The language browsers and servers speak. The client sends a request (a method like GET or
POST, a path, headers, sometimes a body) and the server sends a response (a status code like 200 or
404, headers, a body).
*In our code:* every `/api/...` call; status codes drive classification in `fetcher._classify_status()`.

**REST.** A style of API where URLs name things and HTTP methods say what to do with them: `GET
/api/watches/7` reads watch 7, `PATCH` changes it, `DELETE` removes it.
*In our code:* `routes/watches.py`.

**JSON.** A text format for data: `{"name": "VIT News", "interval_minutes": 60}`.
*In our code:* every API response; JSON columns such as `watch_selectors` and `volatile_rules` in SQLite.

**Cookies and sessions.** A cookie is a small value the browser stores and sends back with every
request to the same site. A session cookie says "this is user 1". We **sign** it with a secret key, so
any edit breaks the signature, and make it **HttpOnly**, so JavaScript (and injected scripts) can't
read it.
*In our code:* `auth.py → set_session_cookie()`, `user_id_from_request()`.

**Password hashing.** We never store passwords. We store a one-way fingerprint made by **Argon2**, which
is deliberately slow and memory-hungry, so a stolen database can't be brute-forced quickly.
*In our code:* `auth.py → hash_password()`, `verify_password()`.

**SQL and indexes.** SQL is the language for asking a database questions. An index is like a book's
index: it lets `WHERE next_fetch_at <= now` find rows without reading the whole table.
*In our code:* `db.py → MIGRATIONS` (`idx_targets_next_fetch`, `idx_watches_target`...).

**Hashing (SHA-256).** A function that turns any text into a fixed 64-character fingerprint. The same
input always gives the same hash, and a tiny change gives a completely different one.
*In our code:* `checker.sha256()` for `content_hash`; `urlnorm.dial_seed()`; alert `dedupe_key`.

**Headless browser.** A real Chrome running without a window. It runs JavaScript, so pages built in the
browser (React, Vue) have their content rendered. A plain HTTP fetch would see an empty shell.
*In our code:* `fetcher.py` (Playwright).

**async/await and the event loop.** One Python thread juggles many tasks. When a task waits for the
network (`await`), the loop runs other tasks meanwhile. That's how one process serves the API, three
workers and the scheduler at the same time.
*In our code:* everywhere; `asyncio.create_task` in `jobqueue.start()` and `scheduler.start()`.

**Job queue and workers.** A waiting line of work plus a few loops that take jobs from it. Priority
lets urgent jobs ("Check now") jump the line.
*In our code:* `jobqueue.py → JobQueue`, `asyncio.PriorityQueue`, `_worker()`.

**Scheduler.** A clock that decides when work is due and puts it in the queue.
*In our code:* `scheduler.py → Scheduler.tick()` every 20 s.

**Timeouts.** A maximum time we're willing to wait, so one slow site can't block a worker forever.
*In our code:* 30 s page load, 45 s per render (`fetcher.RENDER_TIMEOUT_S`), 240 s per job.

**Retries.** Trying again after a failure that might be temporary (timeouts, 5xx), but not after a
permanent one (404).
*In our code:* `jobqueue._run_with_retries()`; `alerts.deliver()` (2 s, 10 s, 30 s).

**Exponential backoff.** Waiting longer after each failure (×2, ×4, ×8), so a broken site isn't
pestered.
*In our code:* `checker.apply_failure()` uses `interval × min(2^failures, 8)`.

**Jitter.** A little randomness in waiting times, so many tasks scheduled for the same moment spread
out instead of all firing together.
*In our code:* `scheduler.jittered()` (±10%) and retry delays (+0–30%).

**Rate limiting.** Allowing at most N actions per time window.
*In our code:* `security.RateLimiter` (10 logins per minute per IP); `politeness.slot()` (one request
per site per 10 s).

**robots.txt.** A file where site owners tell bots what not to fetch. Polite crawlers obey it.
*In our code:* `politeness.robots_allows()`; `/robots.txt` and `/bot` describe our own crawler.

**ETag / 304 Not Modified.** A server can label a page version (`ETag`) or give its last-modified
time. Next time we ask "changed since?" (`If-None-Match`); a `304` means no, so we skip rendering.
*In our code:* `checker.conditional_unchanged()`, used only for pages whose text is in the raw HTML
(`detect_static()`).

**SSRF (server-side request forgery).** Tricking a server into fetching internal addresses (a router,
a cloud metadata service) and leaking the result.
*In our code:* `security.check_url_is_public()`, `is_allowed_subrequest()` (every browser
sub-request), the redirect check in `fetcher._render()`, and `alerts.valid_discord_webhook()`.

**CSP and nonces.** A Content-Security-Policy header tells the browser what a page may load or run. A
nonce is a random one-time value: only `<script nonce="...">` with the right value may run.
*In our code:* `picker/frame.py → build_csp()`, `sanitise()`.

**iframe sandbox and postMessage.** A sandboxed iframe runs its content in an isolated, opaque origin.
It can't touch our cookies or DOM. The two windows talk only by passing messages.
*In our code:* `pages/Picker.tsx` (`sandbox="allow-scripts"`, `event.source` check) and `picker.js`.

**CSRF (cross-site request forgery).** Another website making your browser send a request to ours
using your cookie. We block it with SameSite cookies and by checking the `Origin` header.
*In our code:* `security.OriginCheckMiddleware`, `auth.set_session_cookie(samesite="lax")`.

**SSE (Server-Sent Events).** One long HTTP response that the server keeps writing small events into.
It's one-way (server → browser) and reconnects automatically.
*In our code:* `routes/events.py`, `events.py`, `realtime/useEvents.ts`.

**CORS.** Browser rules for when a page on one origin may read responses from another. We avoid
needing it by serving everything from one origin; it's configurable for split hosting.
*In our code:* `main.py` (`CORSMiddleware` only when `CORS_ORIGINS` is set); the Vite proxy in dev.

**React components, state and hooks.** Components are functions that return UI. State is data that,
when it changes, re-renders the component. Hooks (`useState`, `useEffect`, custom `useX`) let
components hold state and side effects.
*In our code:* every `.tsx` file; custom hooks such as `useSpecular`, `useNow` and `useEvents`.

**TanStack Query.** A library that fetches, caches and refreshes server data for React. Mutations
invalidate cached data so it refetches.
*In our code:* `api/hooks.ts`.

**SPA routing.** The browser loads one HTML page and JavaScript swaps screens as the URL changes, with
no full page reloads. The server must return `index.html` for any app URL.
*In our code:* `App.tsx` (React Router); `main.py → spa()` fallback.

**CSS variables.** Named values like `--accent: #EFA98C` that every style uses. Changing them on one
element re-themes everything beneath it.
*In our code:* `design/tokens.css` (two themes); live `--mx/--my` for the specular light.

**SVG.** Vector graphics described as shapes and paths, sharp at any size.
*In our code:* dials, gears, the jewel, the favicon.

**The diff algorithm (SequenceMatcher).** It finds the longest block of lines common to both versions,
then repeats on the parts before and after. What's left are inserts, deletes and replacements. It runs
on lines, then on words inside edited lines. Worst case O(n²) in lines; fast in practice.
*In our code:* `differ.diff_lines()`, `noise.measure_change()`.

**Idempotency and dedupe keys.** Doing something twice has the same effect as doing it once. A UNIQUE
key per alert makes the database refuse a second copy, so retries and races can't double-send.
*In our code:* `alerts.claim()` + `alerts.dedupe_key` UNIQUE + `db.insert_unique()`.

**Docker.** A recipe (`Dockerfile`) that packages the app and everything it needs into an image that
runs the same everywhere. Ours has two stages: build the frontend, then run the backend with Chromium.
*In our code:* `Dockerfile`, `render.yaml`, `railway.json`.

**Environment variables.** Settings passed to a program from outside, so secrets and per-server values
never live in the code.
*In our code:* `config.py`, `backend/.env.example`.
