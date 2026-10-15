/**
 * time.ts — turning ISO timestamps from the API into words people read.
 *
 * - relative(): "4 minutes ago", "in 11 minutes"
 * - short(): the compact form used in a dial's date window: "now", "5m", "2h", "3d", "—"
 * - exact(): full date and time in the user's timezone (shown on hover)
 * - intervalLabel(): "every hour", "every 15 minutes"
 */

const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

export function toMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

/** "4 minutes ago" / "in 11 minutes" / "just now". */
export function relative(iso: string | null | undefined, now: number = Date.now()): string {
  const t = toMs(iso);
  if (t === null) return 'never';
  const diff = t - now;
  const abs = Math.abs(diff);
  let text: string;
  if (abs < 45_000) return diff > 0 ? 'in a moment' : 'just now';
  if (abs < HOUR) text = plural(Math.round(abs / MIN), 'minute');
  else if (abs < DAY) text = plural(Math.round(abs / HOUR), 'hour');
  else if (abs < 30 * DAY) text = plural(Math.round(abs / DAY), 'day');
  else text = plural(Math.round(abs / (30 * DAY)), 'month');
  return diff > 0 ? `in ${text}` : `${text} ago`;
}

/** Compact date-window text: "now", "5m", "2h", "3d", or an em dash when it never changed. */
export function short(iso: string | null | undefined, now: number = Date.now()): string {
  const t = toMs(iso);
  if (t === null) return '—';
  const abs = Math.max(0, now - t);
  if (abs < MIN) return 'now';
  if (abs < HOUR) return `${Math.floor(abs / MIN)}m`;
  if (abs < DAY) return `${Math.floor(abs / HOUR)}h`;
  if (abs < 100 * DAY) return `${Math.floor(abs / DAY)}d`;
  return `${Math.floor(abs / (30 * DAY))}mo`;
}

/** Full date and time in the given timezone, e.g. "15 Oct 2026, 2:14 PM". */
export function exact(iso: string | null | undefined, timeZone?: string): string {
  const t = toMs(iso);
  if (t === null) return '';
  return new Intl.DateTimeFormat('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true, timeZone,
  }).format(new Date(t));
}

/** Time of day only, e.g. "4:15 PM". */
export function clock(iso: string | null | undefined, timeZone?: string): string {
  const t = toMs(iso);
  if (t === null) return '';
  return new Intl.DateTimeFormat('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone }).format(new Date(t));
}

/** "Today 2:14 PM", "Yesterday 9:02 AM", or "12 Oct, 9:02 AM" — used on the timeline. */
export function dayAndTime(iso: string | null | undefined, timeZone?: string): string {
  const t = toMs(iso);
  if (t === null) return '';
  const fmtDay = new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit', timeZone });
  const today = fmtDay.format(new Date());
  const yesterday = fmtDay.format(new Date(Date.now() - DAY));
  const day = fmtDay.format(new Date(t));
  const time = clock(iso, timeZone);
  if (day === today) return `Today ${time}`;
  if (day === yesterday) return `Yesterday ${time}`;
  const date = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', timeZone }).format(new Date(t));
  return `${date}, ${time}`;
}

/** "every 15 minutes", "every hour", "every 6 hours", "every day". */
export function intervalLabel(minutes: number): string {
  if (minutes === 1440) return 'every day';
  if (minutes === 60) return 'every hour';
  if (minutes % 60 === 0) return `every ${minutes / 60} hours`;
  if (minutes > 60) return `every ${Math.floor(minutes / 60)} h ${minutes % 60} min`;
  return `every ${minutes} minutes`;
}

/** Short interval label for segmented controls: 15m, 1h, 24h. */
export function intervalShort(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  if (minutes % 60 === 0) return `${minutes / 60}h`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

/** Greeting by local hour. */
export function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return 'Good evening';
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}
