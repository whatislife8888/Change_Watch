# Four-minute demo script

**Before you start (5 minutes earlier):**
- Log in as the demo user (`python -m app.seed` creates `demo@changewatch.app` / `watch-the-dials`), or use
  your own account with these pages added: `{BASE_URL}/demo/changing-page`, `{BASE_URL}/demo/bot-check`,
  `{BASE_URL}/demo/outage`, a Wikipedia article and `https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html`
  with number tracking on `p.price_color`.
- Make sure the demo page has at least two versions. Its notice changes every 5 minutes, so wait one cycle.
- Open a second browser profile logged in as a different user, for the "fetched once" moment.

| Time | Click | Say |
|---|---|---|
| 0:00 | Landing page; type a URL into the box | "Every page you watch becomes its own watch dial, engraved from a hash of its address. Same URL, same dial, on any device. Watch it change as I type." |
| 0:20 | Log in → Dashboard | "Each dial carries real state: the jewel is the status, the blued hand shows time until the next check, the date window shows time since the last change. One sentence summarises the day." |
| 0:35 | Point at the Movement | "This is the job queue, live. Three workers, one jewel each. The gears only turn while checks run." |
| 0:45 | A dial's menu → Check now | "A priority job. Watch the lume arc travel while it checks; the Movement turns." *(Requirements 1, 2)* |
| 1:05 | Open the demo page's detail → Activity tab | "This page is designed to be annoying: a new timestamp, token, counter and banner on every load. All ignored. Here: 'Ignored: this part changes on every load, learned 3 new rules'. When a change looks real, we reload ten seconds later and only keep what's in both loads." *(Requirement 4, design question 3)* |
| 1:30 | Settings tab → Learned noise rules | "Here's what it learned, `#tip` for example. Users can delete rules, and the built-in filters are listed." |
| 1:40 | History tab → Compare with previous | "Any two versions. The text view highlights the exact words: the deadline moved and the price changed. Side by side too." *(Requirement 6)* |
| 2:00 | Screenshot tab; move the loupe; hold Space | "The screenshot diff detects if content shifted before comparing. The loupe magnifies, and holding Space shows the older version under the glass." Show Slider and Overlay briefly. |
| 2:25 | Pick regions on the book page; click a paragraph (Watch), the price (Number); Test selection; Save | "The page runs in a sandboxed iframe with every script stripped and a CSP nonce. Each click becomes a stable CSS selector. Saving creates a new starting point, so no false alert." *(Requirement 5)* |
| 2:50 | Numbers tab | "Number tracking: every check records the price; salmon dots mark when the page changed. Threshold alerts fire once per crossing." *(Bonus)* |
| 3:05 | Dashboard: bot-check and outage dials | "Design question 1. A CAPTCHA page is Blocked, not changed. An outage is Error after three retries with backoff. Neither creates a version, and you get one status alert after three failures, then 'Back to normal'." |
| 3:20 | Second browser: add `example.com/?utm_source=x`; the detail page says "N other people watch this page too" | "Design question 2. Tracking parameters are normalised away: one Target, fetched once for everyone." |
| 3:35 | /system (admin) | "Design question 4. Sharing ratio, outcome rates, render time, and when each site may next be contacted. One request per site at least 10 seconds apart, robots.txt respected, and our crawler explains itself at /bot." |
| 3:50 | Settings → Discord → Send test (or show an alert email) | "Alerts go to email, Telegram or Discord, with a summary and a link straight to this comparison, once per change and channel, enforced by a UNIQUE key in the database." *(Requirement 7)* |

**If something goes wrong live:** the Activity tab is the evidence. Every check and its outcome is
logged in plain words.
