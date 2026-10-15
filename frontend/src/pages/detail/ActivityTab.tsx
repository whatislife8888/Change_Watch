/**
 * ActivityTab.tsx — the check log for one page, in plain words ("Unchanged", "Ignored a tiny change",
 * "Couldn't reach the site"...). Shows every attempt, including retries, so you can see the engine work.
 */
import { useChecks } from '../../api/hooks';
import type { CheckLogItem } from '../../api/types';
import { Skeleton, StatusText, Tooltip, type StatusKind } from '../../components/ui/misc';
import { dayAndTime, exact } from '../../lib/time';
import s from './Detail.module.css';

const WORDS: Record<string, [string, StatusKind]> = {
  changed: ['Changed', 'ok'],
  unchanged: ['Unchanged', 'ok'],
  ignored_minor: ['Ignored a tiny change', 'ok'],
  ignored_volatile: ['Ignored: this part changes on every load', 'ok'],
  not_modified: ['Unchanged (the server said nothing changed)', 'ok'],
  error: ["Couldn't reach the site", 'error'],
  timeout: ['Timed out', 'error'],
  blocked: ['Blocked', 'blocked'],
  robots_disallowed: ['Disallowed by robots.txt', 'blocked'],
};

function outcomeWords(item: Pick<CheckLogItem, 'outcome' | 'detail'>): [string, StatusKind] {
  if (item.outcome === 'blocked' && item.detail?.includes('bot check')) return ['Bot check shown', 'blocked'];
  return WORDS[item.outcome] ?? [item.outcome, 'pending'];
}

export function ActivityTab({ watchId, timeZone }: { watchId: number; timeZone?: string }) {
  const { data, isLoading } = useChecks(watchId);
  if (isLoading) return <div className={s.stack}><Skeleton height={44} /><Skeleton height={44} /><Skeleton height={44} /></div>;
  if (!data?.length) return <p className="muted">No checks yet. The first one runs within seconds of adding a page.</p>;
  return (
    <ol className={s.log}>
      {data.map((item) => {
        const [words, kind] = outcomeWords(item);
        return (
          <li key={item.id} className={s.logRow}>
            <Tooltip tip={exact(item.started_at, timeZone)}><span className={`${s.logWhen} num`}>{dayAndTime(item.started_at, timeZone)}</span></Tooltip>
            <span className={s.logOutcome}><StatusText status={kind}>{words}</StatusText></span>
            <span className={s.logDetail}>
              {item.detail && item.outcome !== 'unchanged' ? item.detail : null}
              {item.attempt > 1 ? ` (attempt ${item.attempt})` : ''}
              {item.watch_id === null ? ' Retry scheduled.' : ''}
            </span>
            <span className={`${s.logMs} num`}>{item.duration_ms != null ? `${(item.duration_ms / 1000).toFixed(1)} s` : ''}</span>
          </li>
        );
      })}
    </ol>
  );
}
