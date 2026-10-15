/**
 * Activity.tsx — one feed of changes, errors, blocks and recoveries across all pages, newest first,
 * filterable by page and type. Errors appear once per run (when a page starts failing), not per check.
 */
import { Link } from 'react-router-dom';
import { useState } from 'react';
import { useActivity, useMe, useWatches } from '../api/hooks';
import type { ActivityItem } from '../api/types';
import { Dial } from '../components/dial/Dial';
import { PageShell } from '../components/layout/PageShell';
import { Chip, EmptyState, Skeleton, StatusText, Tooltip, type StatusKind } from '../components/ui/misc';
import { Select } from '../components/ui/Select';
import { dayAndTime, exact } from '../lib/time';
import s from './Activity.module.css';

const KIND: Record<ActivityItem['kind'], [string, StatusKind]> = {
  change: ['Changed', 'ok'],
  first: ['First version', 'pending'],
  baseline: ['New starting point', 'pending'],
  error: ["Couldn't reach", 'error'],
  blocked: ['Blocked', 'blocked'],
  recovered: ['Back to normal', 'ok'],
};

export default function Activity() {
  const { data: me } = useMe();
  const { data: watches } = useWatches();
  const [kind, setKind] = useState<string>('');
  const [watchId, setWatchId] = useState<number | undefined>(undefined);
  const { data, isLoading } = useActivity({ watchId, kind: kind || undefined });
  const tz = me?.timezone;

  return (
    <PageShell>
      <h1>Activity</h1>
      <p className={s.lede}>Every change, outage and bot check across your pages.</p>
      <div className={s.filters}>
        <div className={s.chips} role="group" aria-label="Filter by type">
          <Chip active={kind === ''} onClick={() => setKind('')}>Everything</Chip>
          <Chip active={kind === 'changes'} onClick={() => setKind('changes')}>Changes</Chip>
          <Chip active={kind === 'problems'} onClick={() => setKind('problems')}>Problems</Chip>
        </div>
        <div className={s.select}>
          <Select label="Page" value={watchId ?? ''} onChange={(e) => setWatchId(e.target.value ? Number(e.target.value) : undefined)}>
            <option value="">All pages</option>
            {watches?.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </Select>
        </div>
      </div>
      {isLoading ? (
        <div className={s.list}><Skeleton height={64} /><Skeleton height={64} /><Skeleton height={64} /></div>
      ) : !data?.length ? (
        <EmptyState title="Nothing yet." body="Changes and problems appear here as soon as the engine finds them." />
      ) : (
        <ol className={s.list}>
          {data.map((item, i) => {
            const [word, status] = KIND[item.kind];
            const compare = item.kind === 'change' && item.previous_snapshot_id
              ? `/pages/${item.watch_id}/compare?a=${item.previous_snapshot_id}&b=${item.snapshot_id}` : null;
            return (
              <li key={`${item.kind}-${item.at}-${i}`} className={s.item}>
                <Dial seed={item.dial_seed} size={48} decorative showDate={false} status={status === 'error' ? 'error' : status === 'blocked' ? 'blocked' : 'ok'} />
                <div className={s.body}>
                  <div className={s.top}>
                    <Link to={`/pages/${item.watch_id}`} className={s.name}>{item.watch_name}</Link>
                    <StatusText status={status}>{word}</StatusText>
                  </div>
                  <p className={s.summary}>{item.summary}</p>
                  <div className={s.meta}>
                    <Tooltip tip={exact(item.at, tz)}><span className="num">{dayAndTime(item.at, tz)}</span></Tooltip>
                    {item.kind === 'change' && <span className="num"><span className={s.added}>+{item.added}</span> <span className={s.removed}>&minus;{item.removed}</span></span>}
                    {compare && <Link to={compare}>Compare</Link>}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </PageShell>
  );
}
