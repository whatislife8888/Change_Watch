"""
demo.py — /demo/changing-page: a test page that is noisy on every load and really changes every 5 minutes.

Who uses it: evaluators and the demo script. Enabled by ALLOW_DEMO_PAGE=true (the only URL on our own
host that the SSRF guard lets through).

On EVERY load (noise ChangeWatch should ignore):
  - a fresh timestamp ("Last updated 10:42:07 AM")          → removed by the time rules
  - a random session token                                   → removed by the token rules
  - a rotating promo banner in a .carousel                   → removed by the carousel filter
  - a "people viewing now" counter                           → removed by the counter rule
  - a random "Tip of the moment"                             → learned as volatile after one confirmation re-fetch
Every 5 MINUTES (a real change ChangeWatch should catch exactly once):
  - the announcement headline, the registration deadline and the ticket price
"""
import html
import random
import secrets
import time
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

# (headline, ticket price, a details paragraph). Each 5-minute change is well over 100 characters, so it
# still counts as real even after the flapping guard raises this page's threshold to "low".
ANNOUNCEMENTS = [
    ("Registrations are open for the winter hackathon", 79900,
     "Teams can register on the portal until the deadline. Each team needs a mentor from the faculty list and a short project idea."),
    ("Keynote speaker confirmed: Dr. Meera Iyer on edge AI", 74900,
     "Dr. Iyer leads the embedded systems lab and will talk about running language models on tiny devices, followed by a Q&A session."),
    ("Venue moved to the Anna Auditorium, second floor", 74900,
     "The main hall is being renovated, so all sessions move to the Anna Auditorium. Lifts are available near the east entrance."),
    ("Workshop slots added for Saturday afternoon", 69900,
     "Three new workshops cover web security, Rust for beginners and designing with accessibility in mind. Seats are limited to forty each."),
    ("Early-bird pricing extended for student teams", 64900,
     "Student teams that register this week keep the early-bird price. Bring a valid college ID to the help desk on the first morning."),
    ("Mentor list published: 24 industry mentors", 69900,
     "Mentors from product companies and startups will hold office hours on day two. Book a slot from the schedule page after registering."),
    ("Final round will be streamed live on the college channel", 72900,
     "Finalists present for eight minutes each, followed by questions from the judges. Remote viewers can vote for the audience award."),
    ("Prize pool increased to ₹5,00,000", 72900,
     "The top three teams share the prize pool, and two special awards go to the best first-year team and the most accessible design."),
]
TIPS = [
    "Commit early, commit often.", "Read the error message twice.", "Name things for what they do.",
    "Write the test before the fix.", "Small pull requests get reviewed faster.", "Sleep is a debugging tool.",
    "Logs are love letters to your future self.", "Measure before you optimise.",
]
PROMOS = ["Free stickers at the help desk", "Hoodies now in stock", "Lunch sponsored by the alumni club", "Swag bags for the first 100 teams"]


def render_demo_page() -> str:
    """Build the HTML for one load of the demo page."""
    now = datetime.now(IST)
    bucket = int(time.time() // 300)  # changes every 5 minutes
    headline, price, details = ANNOUNCEMENTS[bucket % len(ANNOUNCEMENTS)]
    deadline = (now + timedelta(days=5 + bucket % 7)).strftime("%d %b")
    token = secrets.token_hex(12)
    viewers = random.randint(120, 980)
    tip = random.choice(TIPS)
    promo = random.choice(PROMOS)
    price_text = f"₹{price:,}"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campus Tech Fest — notice board</title>
<style>
  body {{ font-family: Georgia, serif; margin: 0; background: #f6f3ec; color: #1d2421; }}
  header {{ background: #17392f; color: #ece7dc; padding: 28px 48px; }}
  header h1 {{ margin: 0; font-weight: 400; font-size: 34px; }}
  .meta {{ font-family: system-ui, sans-serif; font-size: 13px; opacity: .8; margin-top: 6px; }}
  .carousel {{ background: #efa98c; color: #0b1411; padding: 10px 48px; font-family: system-ui, sans-serif; }}
  main {{ max-width: 860px; padding: 32px 48px; }}
  #notice {{ border-left: 4px solid #2340c8; padding: 8px 20px; background: #fff; }}
  #notice h2 {{ margin: 0 0 8px; font-weight: 400; }}
  .price {{ font-size: 28px; color: #2340c8; }}
  aside {{ font-family: system-ui, sans-serif; font-size: 14px; color: #4f5754; margin-top: 28px; }}
  footer {{ padding: 24px 48px; font-size: 12px; color: #6c7470; font-family: system-ui, sans-serif; }}
</style></head>
<body>
<header>
  <h1>Campus Tech Fest</h1>
  <div class="meta">Last updated {now.strftime('%I:%M:%S %p')} IST · session {token} · {viewers} people viewing now</div>
</header>
<div class="carousel" role="region" aria-label="Promotions">{html.escape(promo)}</div>
<main>
  <section id="notice">
    <h2>{html.escape(headline)}</h2>
    <p>Registrations close {deadline}. Teams of two to four.</p>
    <p>{html.escape(details)}</p>
    <p class="price">Team pass: {price_text}</p>
  </section>
  <section id="schedule">
    <h3>Schedule</h3>
    <ul><li>Day 1: opening and team formation</li><li>Day 2: build day</li><li>Day 3: demos and awards</li></ul>
  </section>
  <aside><p id="tip">Tip of the moment: {html.escape(tip)}</p></aside>
</main>
<footer>© {now.year} Campus Tech Fest. This page is a ChangeWatch demo: its notice changes every 5 minutes.</footer>
</body></html>"""
