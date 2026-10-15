/**
 * NumbersTab.tsx — the tracked number for a page. The chart arrives in Phase 9; for now this explains
 * how to start tracking and lists recorded values.
 */
import { Link } from 'react-router-dom';
import { useNumbers } from '../../api/hooks';
import type { WatchDetail } from '../../api/types';
import { dayAndTime } from '../../lib/time';

export function NumbersTab({ watch, timeZone }: { watch: WatchDetail; timeZone?: string }) {
  const enabled = !!(watch.number_selector || watch.number_regex);
  const { data } = useNumbers(watch.id, enabled);
  if (!enabled) {
    return (
      <p className="muted">
        Track a price or count on this page and see it as a chart. Choose it with <Link to={`/pages/${watch.id}/picker`}>Pick regions</Link> (Number mode), or set a selector in Settings.
      </p>
    );
  }
  if (!data?.points.length) return <p className="muted">No values recorded yet. One is recorded on every successful check.</p>;
  return (
    <ul>
      {data.points.slice(-20).reverse().map((p) => <li key={p.t}>{dayAndTime(p.t, timeZone)}: {p.raw}</li>)}
    </ul>
  );
}
