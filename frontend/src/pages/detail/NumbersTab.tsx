/**
 * NumbersTab.tsx — the tracked number for a page: a chart over time (salmon dots where the page changed),
 * the lowest / highest / latest values and the change since tracking started. Thresholds are set in Settings.
 */
import { Link } from 'react-router-dom';
import { useNumbers } from '../../api/hooks';
import type { WatchDetail } from '../../api/types';
import { NumberChart, numberFormat } from '../../components/charts/NumberChart';
import { Skeleton } from '../../components/ui/misc';
import s from './Detail.module.css';

export function NumbersTab({ watch, timeZone }: { watch: WatchDetail; timeZone?: string }) {
  const enabled = !!(watch.number_selector || watch.number_regex);
  const { data, isLoading } = useNumbers(watch.id, enabled);
  if (!enabled) {
    return (
      <p className="muted">
        Track a price or count on this page and see it as a chart. Choose it with <Link to={`/pages/${watch.id}/picker`}>Pick regions</Link> (Number mode), or set a selector in Settings.
      </p>
    );
  }
  if (isLoading) return <Skeleton height={280} />;
  if (!data?.points.length) return <p className="muted">No values recorded yet. One is recorded on every successful check.</p>;
  const latestRaw = data.points[data.points.length - 1].raw;
  const pct = data.change_pct;
  const th = watch.number_thresholds;
  return (
    <div className={s.numbers}>
      <dl className={s.figures}>
        <div><dt>Latest</dt><dd>{latestRaw}</dd></div>
        <div><dt>Lowest</dt><dd className="num">{data.min !== null ? numberFormat.format(data.min) : '—'}</dd></div>
        <div><dt>Highest</dt><dd className="num">{data.max !== null ? numberFormat.format(data.max) : '—'}</dd></div>
        <div>
          <dt>Since tracking began</dt>
          <dd className="num">{pct === null || pct === undefined ? '—' : `${pct > 0 ? '+' : pct < 0 ? '−' : ''}${Math.abs(pct).toFixed(1)}%`}</dd>
        </div>
      </dl>
      <NumberChart data={data} label={`${watch.number_selector ?? 'Tracked number'} over time`} timeZone={timeZone} />
      <p className="muted small">
        {th.below != null || th.above != null || th.change_pct != null
          ? `Alerts when it ${[th.below != null && `drops below ${th.below}`, th.above != null && `rises above ${th.above}`, th.change_pct != null && `moves more than ${th.change_pct}%`].filter(Boolean).join(', or ')}.`
          : 'No number alerts yet. Set thresholds in Settings to be told when it crosses a value.'}
        {' '}{data.points.length} value{data.points.length === 1 ? '' : 's'} recorded, one per check.
      </p>
    </div>
  );
}
