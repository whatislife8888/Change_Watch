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
