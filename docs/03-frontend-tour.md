# Frontend tour

React 19 + Vite + TypeScript (strict), React Router, TanStack Query, Motion, Recharts, Sonner. Styling
is CSS Modules plus design tokens (CSS variables), with no component library.

## How data gets from the API to the screen

1. **`api/schema.d.ts`** is generated from the backend's OpenAPI (`npm run gen:api`).
   **`api/types.ts`** gives its shapes friendly names (`WatchSummary`, `CompareResult`...). If a
   backend field changes, TypeScript flags every screen that uses it.
2. **`api/client.ts → api()`** wraps `fetch`: same-origin cookies, JSON in and out, a typed
   `ApiError`, and a redirect to `/login` on 401.
3. **`api/hooks.ts`** has one TanStack Query hook per endpoint (`useWatches`, `useWatch`,
   `useCompare`...). The library caches responses by key, dedupes identical requests and refetches
   on focus. Mutations invalidate the keys they affect. Pausing is optimistic: the dial dims at once
   and rolls back if the server refuses.
4. **`realtime/useEvents.ts`** opens one `EventSource('/api/events')` while you're logged in:
   - `queue` updates a tiny external store that the Movement reads (`useQueueStats`).
   - `check_started` / `check_finished` patch the running flag and refetch the watch, with a tick sound.
   - `change` bumps that watch's engrave counter (`useEngraveKey`) so its dial re-engraves, and shows a
     toast with a Compare action and a chime.
   - After 4 failures it falls back to polling every 30 s.
5. Components read hooks and re-render by themselves.

## Files

| Path | What it does |
|---|---|
| `main.tsx`, `App.tsx` | Entry point. Providers (QueryClient, PrefsProvider, Router), lazy-loaded routes, `RequireAuth`/`GuestOnly`, `LiveEvents`, themed Toaster. `/` shows Landing when logged out and Dashboard when logged in. |
| `design/tokens.css` | Every colour, font, size, radius, shadow and timing for both themes (Fumé on `:root`, Opaline on `[data-theme=opaline]`). `-ink` variants are darker text colours that pass WCAG AA. Self-hosted fonts. |
| `design/global.css`, `textures.css`, `motion.ts` | Base element styles and focus ring; grain, sunburst, Côtes de Genève and shimmer textures; JS easing, durations, the spring, `usePrefersReducedMotion()` |
| `lib/theme.tsx`, `lib/sound.ts` | Theme and sound preferences (localStorage, wrapped in try/catch); Web Audio tick and chime |
| `lib/time.ts`, `lib/useNow.ts` | "4 minutes ago", "5m"/"2h", exact local times, interval labels; a re-render timer |
| `lib/watchStatus.ts`, `lib/keywords.ts` | Jewel and status mapping; parsing `"sold out", restock` |
| `components/dial/*` | The signature dial (below) |
| `components/movement/*` | The live gear train (below) |
| `components/loupe/Loupe.tsx` | The magnifier on the screenshot diff (below) |
| `components/odometer/Odometer.tsx` | Rolling digits |
| `components/diff/*` | Unified diff, side by side, screenshot + loupe, slider (clip-path), overlay (opacity) |
| `components/timeline/Timeline.tsx` | Version history on a blued hairline, with "compare any two" checkboxes |
| `components/charts/NumberChart.tsx` | Tracked number chart (lume line, salmon dots where the page changed, table view) and `Sparkline` |
| `components/forms/WatchFields.tsx` | Interval, sensitivity and keyword controls shared by Add page and Settings |
| `components/layout/*` | Top bar (collapses to a menu on phones), theme and sound toggles, page shell, footer |
| `components/ui/*` | Button (crown-shaped primary with one sheen sweep), Input, Select, SegmentedControl (radiogroup, roving tabindex, sliding thumb), Tabs, Modal (focus handling), Menu (keyboard), Skeleton, EmptyState, StatusText (jewel + word), Tooltip, Chip |
| `components/layout/BottomNav.tsx` | Phone tab bar (Pages, Activity, Add, Settings): icon + word, above the home indicator, only on phone widths for logged-in users |
| `components/layout/Offline.tsx` | `OfflineScreen` (shown instead of logging you out when the server can't be reached; retries every 4 s) and `OfflineBanner`; `useOnline()` |
| `lib/install.ts`, `lib/useMedia.ts` | Service worker registration (production only), the "Install app" prompt (`beforeinstallprompt`), iOS detection, standalone detection; a media-query hook (`PHONE`) |
| `public/manifest.webmanifest`, `public/sw.js`, `public/icons/*` | Installable-app metadata and icons; the service worker (network-first pages, cache-first hashed assets, precache from `asset-manifest.json`, never touches `/api`) |
| `pages/*` | Landing, Login, Signup, Dashboard, AddPage, PageDetail (+ `detail/` tabs), Compare, Picker, Activity, Settings, System, ImportTemplate, NotFound |

## How the signature animations work

### The guilloché (`components/dial/guilloche.ts`)
A plain circle in polar coordinates is `r(θ) = base`, the same radius at every angle. Adding
`A·sin(kθ + φ)` makes the radius wobble k times around the circle, giving a flower with k petals.
Adding a smaller `A2·sin(k·m·θ − φ/2)` puts a finer ripple on each petal. Drawing N of these curves,
each with a slightly larger `base` and a shifted phase `φ`, makes them cross in the interference
pattern that makes guilloché shimmer.

The parameters come from the page's seed. The backend computes `dial_seed` (first 8 hex digits of the
URL's SHA-256). `parseInt(seed, 16)` feeds **mulberry32**, a tiny pseudo-random generator, and we draw
`style, k, N, A, m, A2, turns` in a fixed order. The same URL gives the same numbers and therefore the
same dial on every device. There are four styles: rosette, wave, woven and lattice (two families turning
opposite ways). Paths are cached in memory and sessionStorage.

**Engraving.** Each path gets `pathLength="1"`, which tells the browser to treat the whole curve as
length 1. A dash of length 1 offset by 1 is invisible; animating `stroke-dashoffset` to 0 draws it. A
stagger of 8 ms per line makes the inner lines draw first. Small dials use a cheaper circular
clip-path reveal. *Gotcha we hit:* with `vector-effect: non-scaling-stroke`, Chromium measures dashes
in screen pixels and the animation stopped half-drawn, so the engraving lines use stroke widths in SVG
units instead.

### The sweep hand (`SweepHand.tsx`)
There is no JavaScript per frame. The hand gets one CSS animation lasting `--period` (the check
interval), started in the past with `animation-delay: calc(var(--elapsed) * -1)`. The browser's
compositor turns it smoothly, so 30 dials cost almost nothing. 12 o'clock means just checked; a full
turn means the next check is due. On new data the rotor re-mounts, which re-syncs it. A wrapper plays
a one-time "wind" from 12 o'clock to the true angle (40 ms stagger per dial). With reduced motion
there is no animation; the angle is recomputed every 30 s.

### Specular light and tilt (`useSpecular.ts`)
On `pointermove` we write `--mx/--my` (highlight position) and `--rx/--ry` (tilt, maximum 6°) as CSS
variables directly on the element, inside `requestAnimationFrame`. React doesn't re-render on every
mouse move.

### The Movement (`components/movement/`)
For a gear with `n` teeth and module `m`: pitch radius `rp = m·n/2`, tip `rp + m`, root `rp − 1.25m`,
and each tooth is a trapezoid. Two gears mesh `m(n1+n2)/2` apart, turn in opposite directions, and
their speeds follow `ω2 = −ω1·n1/n2`. That's why each gear's CSS animation duration is scaled by its
tooth ratio. To interlock, gear 2 starts at phase `α + π − π/n2`, so a gap faces gear 1's tooth. Live
`queue` events decide whether the gears run (speed grows with running checks), whether the balance
beats at 1 s or 3 s, and which worker jewels glow.

### The Loupe (`components/loupe/Loupe.tsx`)
A 220 px circle follows the pointer through Motion `useSpring` (stiffness 300, damping 30). Inside it
is a layer as large as the image × zoom, with the screenshot as its background. We translate that
layer by `R − pointer × zoom` so the pixel under the lens centre lines up. Changed regions are drawn on
the same layer. Holding Space swaps the background to the older screenshot. Alt + scroll changes zoom
through a non-passive wheel listener.

### Odometer (`components/odometer/Odometer.tsx`)
Each digit is a 1 em window over a vertical strip of 0–9, and `translateY(-d × 10%)` shows digit d. A
CSS transition with a slightly overshooting curve makes it roll. Tabular figures keep every digit the
same width.

### Landing scroll scene (`pages/Landing.tsx`)
`useScroll` measures progress through a 320vh section with a sticky viewport. `useTransform` maps it to
`rotateX` (0 → 55°), a `spread` value that pushes each layer along Z (`preserve-3d`), and the opacity of
each step label: Render, Filter, Compare, Alert.

### Shared-element transition
Dashboard dials and the detail page's large dial share `layoutId="dial-{id}"`, so Motion animates the
dial growing into the detail page.

### The phone web app (PWA)
- **Manifest.** `manifest.webmanifest` tells the phone the app's name, icons, colours and that it
  should open `standalone` (full screen, no browser bar). The iPhone reads the `apple-*` meta tags in
  `index.html` instead.
- **Service worker** (`public/sw.js`). This is a script the browser runs between the app and the
  network. Page loads try the network first, so you always get the latest deploy, and fall back to the
  cached `index.html` when offline. Files under `/assets/` have a content hash in their names, so they
  are safe to serve from cache forever. A tiny Vite plugin (`vite.config.ts → assetManifest`) lists
  every built file so the worker can cache them all, and old builds' files are deleted. `/api` is never
  cached, so data is always live.
- **Offline vs logged out.** `App.tsx → useAuthState()` returns `offline` when the "who am I" request
  fails with a network error. That's different from a 401 (logged out), so the app shows
  `OfflineScreen` instead of the login page.
- **Safe areas.** `viewport-fit=cover` plus `env(safe-area-inset-*)` padding keep content clear of the
  notch and the home indicator.
- **Touch picker.** In `picker.js`, a touch tap sends `{type:'candidate'}` instead of picking. The
  parent page shows *Select parent / Add / Cancel*, which send `parent`, `confirm` or `cancel` back.
  `atTop` disables *Select parent* when the next step up would be the whole page.
