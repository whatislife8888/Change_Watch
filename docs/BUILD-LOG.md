# Build log

A running record of each build phase and every decision made along the way.

## Decisions

| When | Decision | Why |
|---|---|---|
| Phase 0 | `docs/design/dial-reference.png` was not in the folder, so the dial follows the written spec in Section 13.1 exactly. | The text spec is precise enough (ring radii, jewel position, date window, hand length). |
| Phase 0 | Python 3.14 (the machine's only Python) locally; the Docker image uses the Playwright image's Python. | Spec says 3.11+; every pinned package has 3.14 wheels. |
| Phase 0 | Vite 8 / React 19 / TypeScript 6 (current versions from `npm create vite`). `.npmrc` sets `legacy-peer-deps=true` because `openapi-typescript` still declares a TypeScript 5 peer range. | Newest stable versions; the peer range is only a declaration, it works with TS 6. |
| Phase 0 | Stopped an old uvicorn left running from `~/.Trash/changewatch` that held port 8000. | It belonged to a deleted copy of the project and blocked the dev port. |
| Phase 2 | Added `targets.static_html` and `targets.title` columns. | The 304 pre-check is only safe for pages whose text is in the raw HTML. A JavaScript app can serve the same HTML (same ETag) while its content changes, so for those pages we always render. |

## Phases

### Phase 0 — Scaffold (done 12:08)
1. **What I built:** The empty folder became two apps. A Python FastAPI backend answers on port 8000, and a React + Vite frontend runs on port 5173. Vite forwards every `/api` request to the backend, so the browser only ever talks to one address.
2. **How it works:** (1) The browser opens `localhost:5173`. (2) It asks for `/api/health`. (3) Vite's proxy forwards that to `localhost:8000`. (4) FastAPI answers `{"ok": true}`.
3. **Files:** `CLAUDE.md` (standing rules), `.gitignore`, `dev.sh` (starts both apps), `backend/app/{config,db,main}.py`, `backend/requirements.txt` (pinned), `backend/.env.example`, `frontend/vite.config.ts` (proxy), `frontend/package.json`.
4. **Try it:** `./dev.sh`, then open http://localhost:5173/api/health.
5. **Words to know:** *proxy* (a middleman that forwards requests), *virtualenv* (a private folder of Python packages for one project), *WAL* (SQLite's write-ahead log, so readers and a writer don't block each other), *migration* (a numbered script that upgrades the database schema).
6. **Evaluator question:** "Why a proxy instead of CORS?" With one origin, the session cookie is first-party and needs no CORS configuration. In production, FastAPI serves the built frontend itself, so it's one origin there too.

### Phase 1 — Design system + auth (done 12:26)
1. **What I built:** The look of the whole app: two themes (Fumé dark, Opaline light) as CSS variables, self-hosted fonts, the grain and brushed-metal textures, and the base UI parts (buttons, inputs, tabs, menus, modal). I also built the signature **dial** with its URL-seeded guilloché, plus accounts: sign up, log in, log out, with a signed cookie.
2. **How it works:** (1) Sign up sends the email and password to `POST /api/auth/signup`. (2) The backend hashes the password with Argon2 and stores the user. (3) It signs `{uid}` with `SECRET_KEY` and sets it as an HttpOnly cookie. (4) Every later request carries the cookie, and `current_user()` verifies the signature. (5) POST/PUT/PATCH/DELETE requests must carry an `Origin` header that matches our site (CSRF protection).
3. **Files:** `docs/04-design-system.md`, `frontend/src/design/*` (tokens, global, textures, motion), `components/ui/*`, `components/layout/*`, `components/dial/{guilloche.ts,Dial.tsx,SweepHand.tsx,Jewel.tsx,DateWindow.tsx,useSpecular.ts,Mark.tsx}`, `components/odometer/*`, `pages/{Login,Signup,AuthLayout,NotFound}.tsx`, `backend/app/{auth,security,urlnorm,errors,schemas}.py`, `backend/app/routes/auth.py`.
4. **Try it:** open http://localhost:5173/signup, create an account, then switch theme with the half-circle icon.
5. **Words to know:** *hash* (a one-way fingerprint; we store the fingerprint, never the password), *HttpOnly cookie* (JavaScript can't read it, so injected scripts can't steal the session), *CSRF* (another site making your browser act for you; blocked by the Origin check), *CSS variable* (a named value like `--accent` that a theme can swap), *PRNG* (a seeded random number generator: the same seed always gives the same sequence, so the same URL always gives the same dial).
6. **Evaluator question:** "How is each dial unique and stable?" The backend takes SHA-256 of the normalised URL and keeps the first 8 hex digits as the seed. The frontend feeds that seed into mulberry32 and draws the pattern parameters (style, petals, line count, amplitudes) in a fixed order. Same URL → same seed → same numbers → same dial on every device.

**Decisions:** Opaline status colours that fail AA as text got darker `-ink` variants (jewels keep the spec colours). The guilloché uses stroke widths in SVG units instead of `non-scaling-stroke`, because Chromium measures dashes in screen pixels and the engrave animation would stop half-drawn. Python uses `truststore` (OS certificate store) because this network intercepts TLS.

### Phase 2 — Targets/Watches, fetcher, extraction, first snapshot, Add page, Dashboard (done 12:50)
1. **What I built:** You can now add a page. The backend checks the address is public, then finds or creates one *Target* for that normalised URL and attaches your *Watch* to it. Chromium renders the page within seconds, and the text and screenshot are saved as the first version. The dashboard shows each page as its own dial (List view is a table), and the Add page shows the page's dial changing as you type.
2. **How it works:** (1) Add page → `POST /api/watches`. (2) `normalise_url()` makes `Example.com/?utm_source=x` and `example.com` identical. (3) `check_url_is_public()` resolves DNS and rejects private IPs. (4) `INSERT OR IGNORE` gives one Target per URL. (5) The job queue gets a priority-0 job. (6) A worker renders the page (`fetcher.render`). (7) `extract()` turns HTML into clean text. (8) `normalise_text()` replaces noise with placeholders. (9) The first snapshot is saved with a crop and a 480 px thumbnail.
3. **Files:** `backend/app/{fetcher,extract,noise,checker,views,differ,visual_diff,numbers,summarize,demo,media}.py`, `routes/{watches,public,stats}.py`; `frontend/src/api/{types,hooks}.ts`, `pages/{Dashboard,AddPage,PageDetail}.tsx`, `components/{timeline,forms}/*`, `lib/{keywords,watchStatus,useNow}.ts`.
4. **Try it:** log in → Add page → paste `http://localhost:8000/demo/changing-page` → Add page. You land on its detail page, and the first version appears within seconds.
5. **Words to know:** *Target* (one URL the system fetches), *Watch* (one user's subscription with their own settings), *normalisation* (rewriting equivalent inputs into one canonical form), *SSRF* (tricking a server into fetching internal addresses), *headless browser* (a real Chrome with no window, so JavaScript-built pages render).
6. **Evaluator question:** "If 200 users add the same URL with different tracking parameters, how many fetches?" One per cycle. URL normalisation strips `utm_*`, `fbclid` and the like, `targets.url` is UNIQUE, and every Watch is evaluated from the same render.

### Phase 3 — Scheduler, queue, retries, politeness, classification, SSE, Movement (done 12:52)
1. **What I built:** The engine now runs by itself. A scheduler wakes every 20 s and queues pages that are due. Three workers check them with retries. A politeness layer makes sure no website gets more than one request every 10 s. Outages and bot walls are recognised and never counted as changes. The browser gets live updates, and the dashboard's gear-train "Movement" turns while checks run.
2. **How it works:** (1) `Scheduler.tick()` selects targets whose `next_fetch_at` has passed. (2) `queue.enqueue()` skips anything already queued or running (in-flight dedupe). (3) A worker takes the highest-priority job. (4) `politeness.robots_allows()` and `politeness.slot()` wait for the domain's turn. (5) `fetcher.render()` classifies the result as ok/error/blocked/timeout. (6) A retryable failure waits 5 s → 20 s → 60 s (plus jitter) and tries again. (7) A final failure backs off `interval × 2^n` (capped ×8). (8) Every step is published on the event bus → `/api/events` → `useEvents()` updates the TanStack Query cache.
3. **Files:** `backend/app/{scheduler,jobqueue,politeness,events,maintenance}.py`, `routes/events.py`; `frontend/src/realtime/useEvents.ts`, `components/movement/{gears.ts,Movement.tsx}`.
4. **Try it:** keep the dashboard open and click a dial's menu → Check now. The dial shows a travelling lume arc, the Movement turns, and the hand re-syncs when the check finishes.
5. **Words to know:** *job queue* (a waiting line of work), *worker* (a loop that takes jobs from the queue), *exponential backoff* (wait longer after each failure), *jitter* (a little randomness so retries don't all fire together), *SSE* (Server-Sent Events: one long HTTP response the server keeps writing events into).
6. **Evaluator question:** "Is a CAPTCHA page a change?" No. `fetcher._looks_like_bot_wall()` and `_classify_status()` mark it `blocked` before any diffing, so no snapshot is created and the last good version stays the baseline. After 3 failures you get one status alert, and "Back to normal" when it recovers.
