# Questions evaluators may ask, with answers

## Architecture

**1. Explain the system in one sentence.**
A scheduler puts due pages in a job queue; workers render each page once in headless Chrome, filter out
noise, compare it with the last good version for every user watching it, save a snapshot on a real
change, alert each user once, and push live updates to the browser.

**2. What's the difference between a Target and a Watch?**
A Target is one normalised URL that the system fetches. A Watch is one user's subscription to it, with
their own regions, sensitivity, keywords and alerts. One fetch of a Target serves every Watch on it
(`checker.handle_success`).

**3. If 200 users watch the same URL, is it fetched 200 times?**
No, once per cycle. URLs are normalised (`urlnorm.normalise_url`), `targets.url` is UNIQUE, the queue
dedupes in-flight work, and all 200 watches are evaluated from the same render. The target's interval
is the shortest interval among its watchers.

**4. How do the frontend and backend talk?**
Only through JSON under `/api` and an SSE stream at `/api/events`. In development Vite proxies those to
port 8000; in production FastAPI serves the built frontend, so it's one origin either way.

**5. Why a separate `schemas.py`?**
It's the single source of truth for data shapes. FastAPI publishes it as OpenAPI, and
`npm run gen:api` turns that into TypeScript types, so the two apps can't drift apart.

**6. What happens when I click "Add page"?**
Validate and normalise the URL → SSRF check → find or create the Target → insert the Watch → enqueue at
priority 0 → a worker renders it → extract, normalise, hash → first snapshot + thumbnail → SSE event →
the dial appears. The full trace is in `01-big-picture.md`.

**7. Why does the app look like a watch?**
It's literally a watch for web pages. Each page gets a dial engraved from a hash of its URL, so you
recognise pages at a glance, and the dial's parts carry real state: the hand shows time to the next
check, the jewel shows status, and the date window shows time since the last change.

**8. Is the dial just decoration?**
No. Its parts carry real state (hand, jewel, date window, lume arc while checking), and the pattern is
deterministic from the URL. The Movement on the dashboard is a live view of the queue and workers.

## Scheduling and the queue

**9. How does the scheduler work?**
Every 20 s, `Scheduler.tick()` selects targets whose `next_fetch_at` has passed, that aren't running,
and that have an un-paused watch, then enqueues them at priority 1.

**10. Why add jitter?**
So pages added at the same moment don't all fire together forever. `next_fetch_at` gets ±10%, which
spreads load on our server and on the sites.

**11. How do retries work?**
Up to 3 attempts per job, waiting 5 s, 20 s, then 60 s (plus up to 30% jitter), but only for failures
that might be temporary: timeouts, network errors, 5xx, browser crashes. 4xx errors aren't retried
except 429, where we honour `Retry-After`.

**12. What happens after the final failure?**
The target is marked error or blocked, `consecutive_failures` goes up, and the next attempt is pushed
to `interval × min(2^failures, 8)`. After 3 consecutive failures each watcher gets one status alert,
never a change alert.

**13. What if I click "Check now" while a check is already queued?**
The job queue attaches you to the existing job (and bumps it to priority 0) instead of making a second
one. There's also a 2-minute cooldown per page.

**14. What happens if the server restarts in the middle of a check?**
The job is lost from memory, but the target's `running_since` is reset at startup and its
`next_fetch_at` is still in the past, so the scheduler picks it up again within 20 s. Alerts are
deduplicated in the database, so a repeated check can't send duplicates.

**15. Why a 45-second timeout?**
`page.goto` waits up to 30 s, network-idle up to 8 s, plus settling and the screenshot. 45 s caps the
whole render, so one slow site can't hold a worker hostage.

## Scraping ethics and politeness

**16. How do you avoid hammering a site?**
One request at a time per registrable domain, at least 10 s apart (or the site's Crawl-delay). Plus:
robots.txt, Retry-After, exponential backoff, jitter, a 15-minute minimum interval, a 2-minute manual
cooldown, shared fetching, 304 skips, blocking fonts, media and ads, and a global cap on browser pages.

**17. Do you respect robots.txt?**
Yes. `politeness.robots_allows()` fetches and caches it for 24 hours. A disallowed page is marked
"Blocked: disallowed by robots.txt" and never fetched.

**18. How do sites know who you are?**
Our user agent is `ChangeWatchBot/1.0 (+{BASE_URL}/bot)`, and `/bot` explains what we do and how to
opt out.

**19. Do you bypass CAPTCHAs or log in?**
Never. A bot wall is reported as "Blocked". We store no credentials, reject `user:pass@` URLs, and use
a fresh browser context with no cookies for every check.

**20. What's the 304 trick?**
If a page sends an ETag or Last-Modified header, we first ask "has it changed?" with a cheap HTTP
request. A 304 means no, so we skip Chrome entirely. We only trust this for pages whose text is in the
raw HTML (`detect_static`), because JavaScript apps can serve the same HTML while their content changes.

**21. Why one concurrent request per domain instead of per URL?**
Different URLs on one site usually hit the same servers. We use the registrable domain
(`news.bbc.co.uk` → `bbc.co.uk`, via tldextract), so subdomains share the limit.

## Noise and diffing

**22. Is a site outage or CAPTCHA a change?**
No. Every fetch is classified before diffing: errors and blocks never create snapshots, and the last
good version stays the baseline, so recovery doesn't look like "everything changed". You can see this
live with `/demo/bot-check` and `/demo/outage`.

**23. How do you handle pages that differ on every load?**
When a change is suspected we load the page again 10 s later. Lines that differ between the two loads
are volatile: we learn a text signature and/or the small element they live in, and only changes present
in *both* loads count. The re-fetch only happens on suspected changes, so normal checks cost one request.

**24. What does normalisation do?**
It replaces times, live dates, relative times ("5 minutes ago"), countdowns, view and like counters,
random tokens and copyright years with placeholders before hashing. Prices and plain numbers are left
alone because people care about them.

**25. Why are dates only blanked when they're near today?**
"Updated 15 Oct" on 15 Oct is a live stamp, so it's noise. But "Registrations close 20 Oct" is exactly
the kind of information people watch for. Blanking every date would hide a deadline change.

**26. What does sensitivity do?**
High: any difference. Medium (default): at least 20 changed characters or a whole new line, and at least
0.1% of the text. Low: at least 100 characters and 2%. See `noise.is_significant`.

**27. What's the flapping guard?**
If a page changes 4 or more times in 6 hours, or oscillates A→B→A→B, we raise its threshold one level
for 24 hours, show a notice and send one "this page is changing a lot" message.

**28. How does the text diff work?**
`difflib.SequenceMatcher` on normalised lines decides what changed, then a word-level diff inside each
edited line highlights exactly which words changed. We display raw text, so you read "10:25", not
"<TIME>".

**29. How does the screenshot diff avoid marking everything below an inserted paragraph?**
Shift detection. We find the first differing row, try vertical offsets from −600 to +600 px on small
grayscale copies, align the images at the best one, and only then compare pixels. The UI says
"Content moved down 110 px".

**30. What's the time complexity of your diff?**
SequenceMatcher is O(n²) in the worst case (n = lines). Real pages share long equal runs, so it's near
linear in practice. The word-level diff only runs on changed line pairs.

**31. What are keyword-only alerts?**
Modes: appear (a word newly shows up), disappear (e.g. "Sold out" goes away), and any changed line
mentioning it. Snapshots are still saved; only the alert is filtered, and the triggering keyword is
recorded.

## Alerts

**32. How do you guarantee no duplicate alerts?**
Before sending we insert an `alerts` row with `dedupe_key = sha256(kind:watch:content_hash:channel)`.
The column is UNIQUE, so the database refuses a second row, and we only send if our insert succeeded.
This is safe across retries, restarts and races; a test fires 5 concurrent claims and exactly 1 succeeds.

**33. What if one channel fails?**
Each channel is delivered in its own background task with 3 retries (2 s, 10 s, 30 s). A failing
Telegram never blocks email. Unconfigured channels are recorded as failed with a clear reason.

**34. How does the daily digest work?**
In daily mode, changes are stored as `queued_digest`. Every 10 minutes we check each user's local time,
and after their digest hour we send one grouped message and mark those rows sent. If nothing changed,
nothing is sent.

**35. What's in an alert?**
Page name, URL, time in your timezone, the one-line summary (AI or heuristic), +added/−removed lines,
up to 5 changed lines and a link straight to the comparison. Emails also attach the screenshot with the
changed areas outlined in red.

**36. Can someone use the Discord webhook field for SSRF?**
No. `valid_discord_webhook()` only accepts `https://discord.com/api/webhooks/...` (and the official
alternative Discord hosts).

## Security

**37. How do you stop SSRF?**
We resolve every hostname and reject private, loopback, link-local, multicast and reserved IPs, both
when you add a page and on every fetch. Every sub-request the browser makes is checked too, and the
final URL after redirects is re-checked.

**38. How are passwords stored?**
As Argon2id hashes, never in plain text.

**39. How do sessions work?**
A cookie holding `{uid}`, signed with `SECRET_KEY` (itsdangerous). It's HttpOnly, SameSite=Lax,
Secure in production, and lasts 30 days. Any tampering breaks the signature.

**40. How do you prevent CSRF?**
SameSite=Lax cookies plus an Origin check on every POST/PUT/PATCH/DELETE (`OriginCheckMiddleware`).

**41. Isn't it dangerous to show other websites inside your app (the picker)?**
There are three layers. We strip all scripts and handlers from our stored copy. A CSP header only runs
our one script, carrying a fresh nonce. And the iframe is sandboxed without `allow-same-origin`, so it
can't touch our cookies or DOM. Communication is `postMessage` only, and we check `event.source`.

**42. Can I see other users' screenshots?**
Only for pages you watch yourself (`media.py`). The check log shows only target-level rows and your own
watch's rows.

**43. How is login brute-forcing slowed down?**
10 attempts per minute per IP (sliding window), and the same error message whether the email exists
or not.

## Database

**44. Why SQLite?**
Zero setup, a single file on a persistent disk, and plenty for one server. WAL mode lets readers and
the writer work at the same time. The schema is ordinary SQL, so moving to Postgres would be a
small change.

**45. How do migrations work?**
`db.MIGRATIONS` is an ordered list of SQL scripts plus a `schema_version` table. On startup we run only
the scripts newer than the stored version, so restarts never break the database.

**46. Why store both `text` and `raw_text`?**
`text` is normalised (for comparison); `raw_text` is what people read. Their lines are aligned 1:1, so
a diff decided on normalised lines can display raw lines.

**47. Where do screenshots go?**
Files under `DATA_DIR` (`/data` in production). Fetch files are kept only if a snapshot used them (or
it's the first fetch), and a cleanup task deletes unreferenced ones after 7 days.

**48. What indexes do you have and why?**
`targets(next_fetch_at)` for the scheduler, `watches(target_id)` and `watches(user_id)` for joins,
`snapshots(watch_id, id)` for timelines, and `check_log(target_id, id)` for the activity log and
trimming.

## Frontend and design

**49. How is each dial's pattern made?**
The backend's SHA-256 seed feeds mulberry32, which draws the style, petals, line count and amplitudes.
Each line is the polar curve `r(θ) = base + A·sin(kθ+φ) + A2·sin(kmθ−φ/2)`. The same URL gives the
same dial everywhere.

**50. How do 30 sweep hands animate without lag?**
Each hand is one CSS animation lasting the check interval, started in the past with a negative
`animation-delay`. The compositor does the work, with no JavaScript per frame. Off-screen dials use
`content-visibility: auto`.

**51. How does the dashboard update live?**
`useEvents` listens to SSE and updates the TanStack Query cache. On `change`, the dial re-engraves, the
numbers roll and a toast appears with a Compare link.

**52. How do you handle accessibility?**
Status is always a jewel plus a word, never colour alone. Every text colour passes WCAG AA (we added
darker `-ink` variants where the spec's colours were too light). There's full keyboard navigation
(radiogroups, tabs, menus, the slider handle), a visible blued focus ring, 44 px targets, `role="img"`
labels on dials, and `prefers-reduced-motion` support.

**53. Why no component library?**
To get a distinct look, and because each component is small enough to explain. CSS Modules keep styles
local, and tokens keep them consistent.

**54. How does the Loupe work?**
A circular lens follows the pointer on a spring. Inside it, a layer the size of the image × zoom
carries the screenshot as a background, shifted so the pixel under the lens centre lines up. Holding
Space shows the older version.

**55. How does the picker build a selector?**
Prefer stable over short: a non-random unique id → a unique stable attribute (`data-testid`,
`aria-label`, `name`...) → a `tag.class` path upward using only stable-looking classes, adding
`:nth-of-type` only when needed and stopping as soon as the selector is unique (max depth 6).

## Testing

**56. What did you test?**
129 pytest tests: every normalisation rule (and that prices are untouched), sensitivity thresholds,
flapping, URL normalisation, SSRF, the text and visual diff (including shift detection), number
parsing, keywords, extraction, selectors, fetch classification, and alert dedupe including concurrency.

**57. How did you test end to end?**
On the real running system. The demo page's per-load noise was ignored and a "learned 3 new rules"
entry appeared. Its 5-minute change was caught by the scheduler. The bot-check page was Blocked and
the outage page went to Error after 3 attempts. Two users adding the same URL with different tracking
parameters shared one Target. The picker was driven in a real browser with Playwright.

**58. How did you check the UI?**
Playwright screenshots of each screen at 1440×900 and 390×844 in both themes. We looked at them and
fixed what was wrong: half-drawn engraving, phone overflow, Opaline hand contrast, a wrong timezone in
the dropdown, the scroll scene overlapping its heading.

## Deployment

**59. How is it deployed?**
One Docker container (the frontend is built in stage 1; the backend runs on Microsoft's Playwright
image) with a persistent disk at `/data`, on Render (`render.yaml`) or Railway (`railway.json`). The
health check is `/healthz`.

**60. Why exactly one Uvicorn worker?**
The scheduler, queue and SSE bus live inside the process. A second worker would run a second scheduler
(double checks) and have its own event bus (users on it would miss events).

**61. Why not Vercel for the backend?**
Serverless functions are short-lived and can't keep a browser open or run a scheduler around the clock.

**62. What do I need to configure?**
Only `BASE_URL` and `SECRET_KEY`. Email (SMTP or Resend), Telegram, Discord and AI are optional, and the
UI says "Not set up" without anything failing.

## Scaling

**63. How would you handle a million pages?**
Move the queue to Redis (or a managed queue) and run many stateless browser workers. Move to Postgres
(partition snapshots by time) and S3 for screenshots. Shard the scheduler by target id ranges, keep the
per-domain politeness limits in Redis, use pub/sub for SSE, and lean harder on 304s and region-only
extraction. The Target/Watch split already makes sharing cheap.

**64. What's the current bottleneck?**
Chromium: memory per page and seconds per render. That's why fetches are shared, 304s skip renders,
heavy assets are blocked, and pages are capped (`MAX_BROWSER_PAGES`).

**65. Can it run on multiple servers today?**
Not as is. That's a deliberate trade-off for simplicity. `JobQueue` and `EventBus` are small classes
with narrow interfaces, so swapping in Redis is contained.

## Trade-offs

**66. Why Playwright instead of `requests`?**
Many pages build their content with JavaScript, so `requests` would see an empty shell. We also need
screenshots for the visual diff and element boxes for crops. We still use a plain HTTP request for the
304 pre-check, where it's safe.

**67. Why SSE instead of WebSockets?**
Data only flows server → browser. SSE is plain HTTP, reconnects automatically and works through proxies
with `X-Accel-Buffering: no`.

**68. Why at-most-once alerts instead of at-least-once?**
We save the dedupe row before sending. A crash between the two could lose one alert, but nothing can
ever duplicate one. Duplicate alerts are the thing users hate most, and the change is still in the
timeline, the activity feed and the RSS feed.

**69. Why learn noise rules automatically instead of asking users?**
Most users can't name the noise; they just get annoyed. A 10-second confirmation re-fetch finds it
objectively. Users can still see and delete learned rules, add ignore regions and pick watch regions.

**70. Did you use AI to build this?**
Yes, honestly. I designed the approach and wrote the specification: the Target/Watch split, the noise
layers, the four design questions and the watch-dial design. I built it with an AI coding assistant,
Claude Code. Then I studied every part: the docs in this folder (the big picture, both code tours, the
concepts glossary and these answers) are how I learned it, and I can walk through any file and line.
