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
