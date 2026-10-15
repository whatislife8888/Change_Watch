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

### Phase 4 — Noise pipeline, sensitivity, volatility learning, flapping, keywords, demo page, tests (done 12:57)
1. **What I built:** The layers that stop false alarms. Dates near today, times, countdowns, counters and random tokens become placeholders. Cookie banners, ads, chat widgets and carousels are cut out of the page. When a page looks changed, we load it again 10 s later: whatever differs between those two loads is "volatile", and we learn a rule for it. A sensitivity threshold and a flapping guard sit on top. A demo page is noisy on every load and really changes every 5 minutes.
2. **How it works:** (1) `extract.remove_noise()` deletes noise elements. (2) `noise.normalise_text()` rewrites each line with the regex rules, keeping raw and normalised lines 1:1. (3) If the normalised lines differ from the baseline, `measure_change()` + `is_significant()` apply the sensitivity thresholds. (4) A significant difference triggers a confirmation re-fetch. (5) `learn_rules()` stores a text signature and/or the CSS path of each line that differs between the two fetches. (6) Only changes present in both fetches count (`common_change()`). (7) `after_change()` checks for flapping (≥4 changes in 6 h or A→B→A→B) and raises the threshold for 24 h.
3. **Files:** `backend/app/noise.py` (rules, signatures, thresholds), `extract.py` (`learning_soup`, `css_path`, `element_for_line`), `checker.py` (confirmation + learning), `demo.py`, `tests/test_noise.py`, `tests/test_core.py` (107 tests).
4. **Try it:** `cd backend && .venv/bin/pytest -q`. Then watch the demo page: the first re-check that sees a different "Tip of the moment" logs "Ignored: this part changes on every load — learned 3 new rules", and the 5-minute notice change is caught as a real change.
5. **Words to know:** *regular expression* (a pattern that matches text, like "two digits, a colon, two digits"), *normalisation* (rewriting noise into a fixed placeholder so it hashes the same), *signature* (a fuzzy fingerprint: digits → `#`), *flapping* (a page that keeps switching back and forth).
6. **Evaluator question:** "How do you avoid endless alerts on a page that's different on every load?" Nine layers: regex normalisation, structural removal, ignore regions, watching only a picked region, confirmation re-fetch with learned volatility rules, sensitivity thresholds, keyword mode, the flapping guard and content-hash dedupe. The re-fetch only happens when a change is suspected, so normal checks cost one request.

**Decision:** dates are blanked only when they fall within 2 days of the check. A live "Updated 15 Oct" stamp is noise, but "Registrations close 20 Oct" is the information users watch for, and the spec's own example change ("deadline moved to 20 Oct") would be invisible if every date were blanked.

### Phase 5 — Diffs, shift-aware screenshot diff, Compare (five views + Loupe), timeline, Activity (done 12:58)
1. **What I built:** A Compare screen for any two versions of a page. It has five views: unified text diff, side by side, screenshot with glowing changed regions and a magnifying loupe, a draggable before/after slider, and an onion-skin overlay. The page's History timeline lets you tick any two versions to compare them.
2. **How it works:** (1) `GET /api/watches/{id}/compare?a=&b=`. (2) Both snapshots are re-normalised with today's rules (re-extracted from stored HTML if an element rule is newer). (3) `differ.diff_lines()` runs SequenceMatcher on the normalised lines, then on words inside each edited pair, and returns raw text for display. (4) `visual_diff.compare_images()` detects vertical shift, aligns the images, thresholds the pixel difference, dilates it, groups 16 px cells with a flood fill into rectangles, and caches the result. (5) The frontend draws the ops and regions. The Loupe slides a zoomed background layer under a circular lens.
3. **Files:** `backend/app/{differ,visual_diff}.py`, `routes/watches.py` (compare); `frontend/src/components/diff/*`, `components/loupe/Loupe.tsx`, `components/timeline/Timeline.tsx`, `pages/Compare.tsx`, `pages/detail/ActivityTab.tsx`.
4. **Try it:** open the demo page's detail → Compare versions → Screenshot. Move the mouse over the image and hold Space to see the older version inside the lens.
5. **Words to know:** *SequenceMatcher* (finds the longest common runs of lines between two versions), *dilation* (growing changed pixels so nearby specks merge into one region), *flood fill* (grouping touching cells into one region), *clip-path* (CSS that shows only part of an element, used by the slider).
6. **Evaluator question:** "If a paragraph is inserted at the top, doesn't the whole screenshot look changed?" No. `detect_shift()` finds the first differing row, tries offsets from −600 to +600 px on downscaled copies, and keeps the best match. The rest of the page is compared after aligning, so only the inserted block is highlighted, and the UI says "Content moved down 110 px".

### Phase 6 — Visual picker (done 13:01)
1. **What I built:** A "Pick regions" screen. It shows our stored copy of the page in a locked-down frame. You click parts to watch (green), to ignore (red), or a number to track (blue), and the app turns each click into a stable CSS selector. "Test selection" previews exactly which text would be compared. Saving makes a "New starting point" version, so changing what you watch never fires an alert.
2. **How it works:** (1) `POST /picker/session` returns a frame URL with a signed 10-minute token. (2) `GET /picker/frame` loads the latest stored HTML, and `frame.sanitise()` removes scripts, `on*` handlers, iframes, `javascript:` links and meta refresh, adds `<base href>`, and injects `picker.js` with a random nonce. (3) The CSP header allows only scripts with that nonce. (4) The frontend embeds it with `sandbox="allow-scripts"` (no same-origin). (5) `picker.js` builds a selector (stable id → stable attribute → `tag.class` path with `:nth-of-type` only when needed) and `postMessage`s it up. (6) The parent accepts messages only from that iframe's window. (7) `PUT /selectors` validates the selectors, saves them, and calls `checker.rebaseline()`.
3. **Files:** `backend/app/picker/{picker.js,picker.css,frame.py}`, `routes/picker.py`; `frontend/src/pages/Picker.tsx`.
4. **Try it:** open a page → Pick regions → click a paragraph (Watch) → switch to Number → click a price → Test selection → Save.
5. **Words to know:** *CSS selector* (an address for an element, like `#notice > p`), *sandboxed iframe* (a frame whose content can't touch the parent page or its cookies), *postMessage* (the only safe way for two windows to talk), *CSP nonce* (a one-time random value; only scripts carrying it may run).
6. **Evaluator question:** "Isn't it dangerous to show someone else's page inside your app?" There are three independent layers. We strip every script and handler from our stored copy. The CSP header only runs our one script, which carries a fresh random nonce. And the iframe sandbox has no `allow-same-origin`, so even if something slipped through it runs in an opaque origin with no access to our cookies or DOM.

### Phase 7 — Alerts (email/Telegram/Discord), dedupe, retries, status alerts, digest, Settings, Activity (done 13:12)
1. **What I built:** Real alerts. When a page changes you get one message per channel you turned on: an email with the highlighted screenshot, a Telegram message, or a Discord embed. Each has the summary, the changed lines and a link straight to the comparison. You can switch to one daily digest instead. Pages that can't be reached send one "We can't reach this page" message after 3 failures, and one "Back to normal" when they recover. Settings has a "Send test" button for every channel, and Activity shows everything across all pages.
2. **How it works:** (1) The checker calls `alerts.on_change()`. (2) For each enabled channel, `claim()` INSERTs an `alerts` row whose `dedupe_key = sha256("change:{watch}:{content_hash}:{channel}")` is UNIQUE. (3) If the insert fails, it was already handled, so we skip. (4) Otherwise `spawn(deliver())` sends in the background with retries after 2, 10 and 30 s. (5) In daily mode the row is stored as `queued_digest` instead, and `digest.send_digest()` groups them once a day after the user's local hour.
3. **Files:** `backend/app/{alerts,digest}.py`, `routes/settings.py`, `tests/test_alerts.py`; `frontend/src/pages/{Settings,Activity}.tsx`.
4. **Try it:** Settings → Discord → paste a webhook → Save → Send test. Email needs `SMTP_USER`/`SMTP_PASSWORD` (a Gmail App Password) or `RESEND_API_KEY` in `backend/.env`.
5. **Words to know:** *idempotent* (doing it twice has the same effect as once), *UNIQUE constraint* (the database refuses duplicate values in a column), *webhook* (a URL you POST to so another app receives a message), *SMTP* (the protocol for sending email).
6. **Evaluator question:** "What if the server crashes after sending but before saving that it sent?" We save first (the claim), then send. A crash between them can at worst lose one alert, never duplicate it. The alert row stays `queued` and is visible, and the next *different* change alerts normally. We chose at-most-once delivery because duplicate alerts are the main thing users hate.

### Deployment decisions (15:58)
| Decision | Why |
|---|---|
| Deploy target changed from Railway to **Render**, at your request (you push to GitHub and deploy from Render). Added `render.yaml` (a Blueprint: Docker web service, 1 instance, disk at `/data`, `/healthz` health check). `railway.json` stays for anyone who prefers Railway. | Same single-container design works on both. |
| Render plan `starter` with `MAX_BROWSER_PAGES=1`, `WORKER_COUNT=2`. | Free instances can't have a disk and sleep when idle, which stops the scheduler. Starter has 512 MB of memory, so one Chromium page at a time is the safe setting. |
| Playwright pinned to 1.63.0 (was 1.64.0) to match the newest official Docker image, `mcr.microsoft.com/playwright/python:v1.63.0-noble`. | The spec requires the pip version and the image tag to match exactly. |
| Added `/demo/bot-check` (fake "Just a moment" wall) and `/demo/outage` (always 503) next to `/demo/changing-page`, all three whitelisted only on our own host. | Lets evaluators see design question 1 live: Blocked and Error, never a change. |

### Phase 8 — Deployment prep (done; you deploy on Render)
1. **What I built:** Everything needed to run ChangeWatch as one container on a server: a two-stage `Dockerfile` (build the React app, then run FastAPI on Microsoft's Playwright image), `render.yaml` (Render Blueprint with a disk at `/data`), `railway.json`, and `.dockerignore`.
2. **How it works:** (1) Render builds the Dockerfile. (2) Stage 1 runs `npm ci && npm run build`. (3) Stage 2 installs the Python packages and copies in the built frontend. (4) Uvicorn starts with exactly one worker. (5) `/healthz` reports DB, browser and queue.
3. **Files:** `Dockerfile`, `.dockerignore`, `render.yaml`, `railway.json`.
4. **Try it:** push to GitHub → Render → New → Blueprint → set `BASE_URL` → open `/healthz`.
5. **Words to know:** *container* (a packaged app with everything it needs), *volume/disk* (storage that survives redeploys), *health check* (a URL the host polls to know the app is alive).
6. **Evaluator question:** "Why only one Uvicorn worker?" The scheduler, queue and event bus live in the process; two workers would mean two schedulers (double checks) and two event buses (missed live updates).

### Phase 9 — Bonus features (done 15:40)
Number tracking with a chart (change markers, table view, thresholds), AI one-line summaries (Anthropic Messages API through raw httpx, as specified, with heuristic fallback; `thinking` is disabled for Haiku so its thinking can't use up the 80-token budget), per-page RSS, shared setups (`/import/{token}`), the System view, sparklines and the seed script.
**Evaluator question:** "What if the AI is down?" `ai_summary()` returns `None` on any timeout, refusal or error, and the heuristic summary is used. Alerts never wait more than 15 s on it, and it's never called for ignored changes.

### Phase 10 — Landing page and polish (done 16:00)
A landing page with a hero dial that shows the current time and morphs to a typed URL's dial, an exploded-view scroll scene (Render → Filter → Compare → Alert) and the four hard questions. Lenis smooth scrolling runs on this page only. Screenshots were reviewed at 1440 and 390 px in both themes: no horizontal scroll on any of the 10 screens.

### Phase 11 — Docs, README, acceptance checks (done 17:20)
Wrote `01`–`07` docs and the README with screenshots. Acceptance checks run against the live system:
- Two users adding the same URL with different `utm`/case share **one Target** ("fetched once for everyone").
- `localhost`, `127.0.0.1`, `192.168.x.x`, `169.254.169.254` → `unsafe_url`; `user:pass@` → `invalid_url`; intervals 14 and 2000 → `interval_out_of_range`.
- First snapshot in about 2 s; unchanged re-checks create no snapshot.
- Demo page: per-load noise ignored ("learned 3 new rules"); the 5-minute change was detected by the scheduler and alerted once per channel.
- `/demo/outage`: 3 attempts honouring Retry-After → Error, no snapshot; after 3 consecutive failures exactly **one** status alert. `/demo/bot-check` → Blocked.
- robots.txt: `google.com/search` → "Blocked: robots.txt asks bots not to fetch this page".
- Picker driven in a real browser (watch region, number region, test, save, re-baseline).
- 130 pytest tests pass, including dedupe under 5 concurrent claims and the daily digest batching 3 changes into 1 message.

**Bugs found and fixed during checks:**
- Recharts needed `react-is`, which `legacy-peer-deps` didn't install. The dashboard broke in dev and the Docker build would have failed. Installed it, moved `Sparkline` out of the chart file, and lazy-loaded the chart.
- A DNS failure on an *existing* page was treated as permanent. It is now a retryable network error.
- The in-memory politeness limiter forgot recent requests after a restart (one 6.4 s gap). It is now restored from the fetch log on startup.
- The flapping guard (correctly) raised the demo page's threshold. The demo's 5-minute changes are now large enough to still count, so the demo shows both behaviours.

**Still needs you:** pushing to GitHub and deploying on Render (and then telling me the URL so the README can link it); optional credentials for email (Gmail App Password or Resend), Telegram (bot token) and AI (`ANTHROPIC_API_KEY`). The Docker image wasn't built locally (no Docker on this Mac), so the first Render build is its first real test.

### Phase 12 — Mobile web app (PWA), at your request
1. **What I built:** ChangeWatch now installs on a phone's home screen and opens full screen like an app. Phones get a bottom tab bar, layout that clears the notch, finger-sized controls, and a touch version of the region picker. The app also opens offline and recovers by itself when the connection returns.
2. **How it works:** (1) `index.html` links `manifest.webmanifest` (name, icons, standalone display) and the iPhone meta tags. (2) `lib/install.ts` registers `sw.js` in production and keeps the browser's install event for Settings → App. (3) `sw.js` caches the app shell and every built file listed in `asset-manifest.json`, but never `/api`. (4) `useAuthState()` separates "offline" from "logged out". (5) `BottomNav` appears on phone widths. (6) In the picker, a touch tap selects a candidate, and the parent page sends `parent`, `confirm` or `cancel`.
3. **Files:** `frontend/public/{manifest.webmanifest,sw.js,icons/*}`, `frontend/index.html`, `frontend/vite.config.ts` (asset-manifest plugin), `src/lib/{install,useMedia}.ts`, `src/components/layout/{BottomNav,Offline}.tsx`, `TopBar.tsx`, `App.tsx`, `Settings.tsx`, `Picker.tsx`, `backend/app/picker/picker.js`, `backend/app/main.py` (manifest MIME type, no-cache for `sw.js`, HEAD support).
4. **Try it:** deploy, open it on your phone, then Settings → App → Install (Android) or Share → Add to Home Screen (iPhone). Turn on airplane mode and open it: you see "You're offline". Turn it off and the app comes back by itself.
5. **Words to know:** *PWA* (a website that can be installed and work offline like an app), *service worker* (a background script between the app and the network), *manifest* (the app's name, icons and launch settings), *safe area* (screen space not covered by the notch or home bar).
6. **Evaluator question:** "Can a cached old version get stuck on someone's phone?" No. Page loads are network-first, the service worker and manifest are served with `no-cache`, and cached files have content hashes in their names. A new deploy is picked up on the next online launch, and the old build's files are deleted.

**Bugs found while testing on an emulated iPhone, and fixed:**
- After logging in through the form, components that stay on screen (the new tab bar, and also the live-events connection) didn't notice the login until a reload. `queryClient.clear()` deleted the "who am I" query they were listening to. Now every other cached query is cleared and that one is updated in place.
- Opening the app offline sent people to the login page (and crashed on an uncached screen). It now shows an offline screen and precaches every screen's code.
- "Select parent" did nothing on pages whose content sits directly in `<body>` (the new example.com). The button now disables itself and says why.
