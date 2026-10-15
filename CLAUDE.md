# ChangeWatch — standing notes for Claude Code

## What this project is
ChangeWatch is a website change detector built for VinnovateIT Round 1. Users add a public URL with a
check interval (15 min – 24 h). A Python backend renders the page in a headless Chromium browser on a
schedule, strips noise (timestamps, counters, ads, rotating banners, random tokens), hashes the cleaned
text, stores a new snapshot only when the hash changes, and alerts by email / Telegram / Discord with a
link to a text + screenshot diff. A React frontend shows every watched page as its own engraved watch
dial (a guilloché pattern generated from the URL). The key architectural idea is **Targets vs Watches**:
one Target per normalised URL is fetched once per cycle, and every user's Watch on it is evaluated from
that same fetch.

## Folder map
```
backend/          FastAPI + Playwright + SQLite (aiosqlite). The engine and the JSON API.
  app/            main.py (startup), config, db, auth, security, urlnorm, fetcher, politeness,
                  jobqueue, scheduler, extract, noise, differ, visual_diff, checker, alerts,
                  digest, summarize, numbers, rss, events, media, demo, seed, picker/, routes/
  tests/          pytest unit tests (noise rules, sensitivity, diff, dedupe, urlnorm, SSRF, numbers)
frontend/         React + Vite + TypeScript (strict). Everything the user sees.
  src/api/        fetch client, generated OpenAPI types, TanStack Query hooks
  src/realtime/   SSE hook (live updates)
  src/design/     tokens.css (both themes), global.css, textures.css, motion.ts
  src/components/ dial/, movement/, loupe/, odometer/, diff/, timeline/, charts/, layout/, ui/
  src/pages/      one file (+ .module.css) per route
docs/             Explanations, Q&A, demo script, design system, BUILD-LOG.md
Dockerfile        Multi-stage: builds the frontend, then runs the backend which serves it
dev.sh            Starts backend (8000) and frontend (5173) together
```

## How to run
- Backend: `cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000`
  (first time: `python3 -m venv .venv && pip install -r requirements.txt && playwright install chromium && cp .env.example .env`)
- Frontend: `cd frontend && npm install && npm run dev` → http://localhost:5173 (proxies /api, /rss, /demo, /healthz, /bot to 8000)
- Both at once: `./dev.sh`
- Tests: `cd backend && .venv/bin/pytest -q`
- Frontend type check + build: `cd frontend && npm run build`
- Regenerate API types (backend must be running): `cd frontend && npm run gen:api`
- Seed demo data: `cd backend && .venv/bin/python -m app.seed`

## Code conventions
- Every file starts with a header comment: what it does, who uses it, what it depends on.
- Every function / class / React component has a plain-English docstring or JSDoc explaining **why** it exists.
- Clear over clever. Type hints everywhere in Python; `strict: true` TypeScript.
- Backend response shapes live in `backend/app/schemas.py` (Pydantic) — the single source of truth.
  The frontend mirrors them in `src/api/types.ts` (built on generated `schema.d.ts`).
- The frontend never touches the database; it only calls `/api/...` and listens to `/api/events` (SSE).
- Never commit secrets. Never fake functionality.
- Timestamps are ISO-8601 UTC strings in the DB.
- Exactly one Uvicorn worker in production (scheduler, queue and SSE bus are in-process).

## Design rules (Section 12 in brief)
- Concept: haute horlogerie. Each watched page is a watch dial with a guilloché pattern from its URL seed.
- Two themes: **Fumé** (dark green fumé, salmon engraving, blued hands) and **Opaline** (silver, blued engraving).
- Fonts: Zodiak (display, 300–400 only), Switzer (UI), JetBrains Mono (diffs only).
- CSS Modules + CSS variables. No Tailwind, no component libraries.
- Boldness only in the dials; everything else quiet: hairlines, generous space, left-aligned.
- Motion explains state: one orchestrated load moment per page; respect `prefers-reduced-motion`.
- Status is never colour alone: jewel + word. OK = lume, error = ruby, blocked = topaz, pending = moonstone.
- Copy: sentence case, plain words, no exclamation marks, no emoji, no "Oops".
- Avoid: identical card grids with grey shadows, ALL-CAPS eyebrow labels, " · " metadata joins, "→" on
  buttons, glassmorphism, gradient text, purple AI gradients.
- WCAG AA contrast, keyboard navigation, visible blued focus ring, 44 px touch targets, works at 360 px.

## Standing rules
- After any change, explain what changed and why in simple language.
- When asked "explain X", explain it like to a first-year CS student: start with a real-world analogy,
  then the actual mechanism, then point to the exact file, function and line numbers.
- Keep `docs/` up to date whenever behaviour changes. Log decisions in `docs/BUILD-LOG.md`.
