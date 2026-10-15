/**
 * Dashboard.tsx — "Pages": every watched page as an engraved dial (or a table in List view).
 *
 * - A plain-language summary sentence instead of stat tiles, with numbers that roll (Odometer).
 * - Filter chips (All / Changed today / Needs attention / Paused), search, Dials | List toggle.
 * - The Movement (top right) shows the job queue working in real time.
 * - Live: SSE events update dials without refreshing (see realtime/useEvents.ts).
 * - Orchestrated load moment: every dial winds its hand from 12 o'clock with a 40 ms stagger while the
 *   engraving reveals itself.
 */
import { DotsThreeVertical, MagnifyingGlass } from '@phosphor-icons/react';
import clsx from 'clsx';
import { useMemo, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ApiError } from '../api/client';
import { useCheckNow, useDeleteWatch, useMe, useOverview, useUpdateWatch, useWatches } from '../api/hooks';
import type { WatchSummary } from '../api/types';
import { Sparkline, numberFormat } from '../components/charts/NumberChart';
import { Dial } from '../components/dial/Dial';
import { PageShell } from '../components/layout/PageShell';
import { Movement } from '../components/movement/Movement';
import { Odometer } from '../components/odometer/Odometer';
import { Button } from '../components/ui/Button';
import { Menu } from '../components/ui/Menu';
import { Chip, EmptyState, Skeleton, StatusText, Tooltip } from '../components/ui/misc';
import { Modal } from '../components/ui/Modal';
import { SegmentedControl } from '../components/ui/SegmentedControl';
import { useEngraveKey } from '../realtime/useEvents';
import { exact, greeting, intervalShort, relative } from '../lib/time';
import { useNow } from '../lib/useNow';
import { jewelFor, statusKindFor, statusLine } from '../lib/watchStatus';
import s from './Dashboard.module.css';

type Filter = 'all' | 'changed' | 'attention' | 'paused';
type View = 'dials' | 'list';

const DAY_MS = 24 * 3600 * 1000;

function matches(w: WatchSummary, filter: Filter, q: string, now: number): boolean {
  if (q && !`${w.name} ${w.url}`.toLowerCase().includes(q.toLowerCase())) return false;
  if (filter === 'changed') return !!w.last_changed_at && now - Date.parse(w.last_changed_at) < DAY_MS;
  if (filter === 'attention') return !w.paused && (w.status === 'error' || w.status === 'blocked');
  if (filter === 'paused') return w.paused;
  return true;
}

function readView(): View {
  try {
    return localStorage.getItem('cw-view') === 'list' ? 'list' : 'dials';
  } catch {
    return 'dials';
  }
}

/** Shared actions for a watch (dial menu and table row menu). */
function useWatchActions(w: WatchSummary, onDelete: () => void) {
  const navigate = useNavigate();
  const checkNow = useCheckNow();
  const update = useUpdateWatch(w.id);
  return [
    {
      label: 'Check now',
      onSelect: () => checkNow.mutate(w.id, {
        onSuccess: (r) => toast(r.attached ? 'Already in the queue. It will run shortly.' : 'Check queued.'),
        onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not queue the check.'),
      }),
      disabled: w.paused,
    },
    { label: w.paused ? 'Resume' : 'Pause', onSelect: () => update.mutate({ paused: !w.paused }) },
    { label: 'Edit', onSelect: () => navigate(`/pages/${w.id}?tab=settings`) },
    { label: 'Delete', onSelect: onDelete, danger: true },
  ];
}

function DialCard({ w, index, onDelete }: { w: WatchSummary; index: number; onDelete: (w: WatchSummary) => void }) {
  const engraveKey = useEngraveKey(w.id);
  const actions = useWatchActions(w, () => onDelete(w));
  const line = statusLine(w);
  return (
    <li className={s.card}>
      <Link to={`/pages/${w.id}`} className={s.cardLink}>
        <Dial
          seed={w.dial_seed}
          size={168}
          status={jewelFor(w)}
          paused={w.paused}
          running={w.is_running}
          name={w.name}
          lastCheckedAt={w.last_checked_at}
          lastChangedAt={w.last_changed_at}
          nextDueAt={w.next_due_at}
          intervalMinutes={w.interval_minutes}
          engraveKey={engraveKey}
          engrave
          windIndex={index}
          interactive
          layoutId={`dial-${w.id}`}
        />
        <span className={s.cardName}>{w.name}</span>
        <span className={s.cardDomain}>{w.domain}</span>
        {line && <span className={clsx(s.cardStatus, s[`st_${statusKindFor(w)}`])}>{line}</span>}
      </Link>
      <div className={s.cardMenu}>
        <Menu label={`Actions for ${w.name}`} triggerClassName={s.menuBtn} trigger={<DotsThreeVertical size={20} weight="bold" />} items={actions} />
      </div>
    </li>
  );
}

type SortKey = 'name' | 'status' | 'last_checked_at' | 'last_changed_at' | 'next_due_at' | 'interval_minutes' | 'versions' | 'shared_watchers';

function Row({ w, onDelete, now }: { w: WatchSummary; onDelete: (w: WatchSummary) => void; now: number }) {
  const actions = useWatchActions(w, () => onDelete(w));
  return (
    <tr>
      <td data-label="Page">
        <Link to={`/pages/${w.id}`} className={s.rowName}>{w.name}</Link>
        <span className={s.rowDomain}>{w.domain}</span>
        {w.number_spark.length > 1 && (
          <span className={s.rowNumber}><Sparkline values={w.number_spark} /> <span className="num">{w.number_latest !== null ? numberFormat.format(w.number_latest) : ''}</span></span>
        )}
      </td>
      <td data-label="Status"><StatusText status={statusKindFor(w)} /></td>
      <td data-label="Last checked" className="num"><Tooltip tip={exact(w.last_checked_at)}><span>{relative(w.last_checked_at, now)}</span></Tooltip></td>
      <td data-label="Last changed" className="num"><Tooltip tip={exact(w.last_changed_at)}><span>{w.last_changed_at ? relative(w.last_changed_at, now) : 'Not yet'}</span></Tooltip></td>
      <td data-label="Next check" className="num">{w.paused ? '—' : relative(w.next_due_at, now)}</td>
      <td data-label="Interval" className="num">{intervalShort(w.interval_minutes)}</td>
      <td data-label="Versions" className="num">{w.versions}</td>
      <td data-label="Shared" className="num">{w.shared_watchers > 1 ? `${w.shared_watchers} people` : 'Only you'}</td>
      <td className={s.rowMenu}>
        <Menu label={`Actions for ${w.name}`} triggerClassName={s.menuBtn} trigger={<DotsThreeVertical size={20} weight="bold" />} items={actions} />
      </td>
    </tr>
  );
}

function WatchTable({ watches, onDelete, now }: { watches: WatchSummary[]; onDelete: (w: WatchSummary) => void; now: number }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'name', dir: 1 });
  const sorted = useMemo(() => {
    const copy = [...watches];
    copy.sort((a, b) => {
      const va = a[sort.key] ?? '';
      const vb = b[sort.key] ?? '';
      return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir;
    });
    return copy;
  }, [watches, sort]);
  const header = (key: SortKey, label: string) => (
    <th aria-sort={sort.key === key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
      <button type="button" className={s.sortBtn} onClick={() => setSort((p) => ({ key, dir: p.key === key ? (p.dir === 1 ? -1 : 1) : 1 }))}>
        {label}
        {sort.key === key && <span aria-hidden="true">{sort.dir === 1 ? ' ↑' : ' ↓'}</span>}
      </button>
    </th>
  );
  return (
    <div className={s.tableWrap}>
      <table className={s.table}>
        <thead>
          <tr>
            {header('name', 'Page')}
            {header('status', 'Status')}
            {header('last_checked_at', 'Last checked')}
            {header('last_changed_at', 'Last changed')}
            {header('next_due_at', 'Next check')}
            {header('interval_minutes', 'Interval')}
            {header('versions', 'Versions')}
            {header('shared_watchers', 'Shared')}
            <th><span className="visually-hidden">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((w) => <Row key={w.id} w={w} onDelete={onDelete} now={now} />)}
        </tbody>
      </table>
    </div>
  );
}

function EmptyDashboard() {
  const navigate = useNavigate();
  const [url, setUrl] = useState('');
  function submit(e: FormEvent) {
    e.preventDefault();
    navigate(url.trim() ? `/pages/new?url=${encodeURIComponent(url.trim())}` : '/pages/new');
  }
  return (
    <div className={s.empty}>
      <div className={s.emptyDial} aria-hidden="true">
        <Dial seed="00c0ffee" size={360} decorative engrave status="pending" showDate={false} />
      </div>
      <EmptyState title="You're not watching any pages yet." body="Paste a link to start. Every page gets its own dial, engraved from its address.">
        <form onSubmit={submit} className={s.emptyForm}>
          <label htmlFor="empty-url" className="visually-hidden">Page address</label>
          <input id="empty-url" className={s.emptyInput} placeholder="https://example.com/page" value={url} onChange={(e) => setUrl(e.target.value)} />
          <Button type="submit" variant="primary">Add page</Button>
        </form>
      </EmptyState>
    </div>
  );
}

export default function Dashboard() {
  const { data: user } = useMe();
  const { data: watches, isLoading } = useWatches();
  const { data: overview } = useOverview();
  const del = useDeleteWatch();
  const now = useNow();
  const [filter, setFilter] = useState<Filter>('all');
  const [q, setQ] = useState('');
  const [view, setViewState] = useState<View>(readView);
  const [toDelete, setToDelete] = useState<WatchSummary | null>(null);

  const setView = (v: View) => {
    setViewState(v);
    try { localStorage.setItem('cw-view', v); } catch { /* ignore */ }
  };

  const list = watches ?? [];
  const visible = list.filter((w) => matches(w, filter, q, now));
  const counts = {
    all: list.length,
    changed: list.filter((w) => matches(w, 'changed', '', now)).length,
    attention: list.filter((w) => matches(w, 'attention', '', now)).length,
    paused: list.filter((w) => w.paused).length,
  };
  const total = overview?.total ?? counts.all;
  const changed = overview?.changed_today ?? counts.changed;
  const attention = overview?.needs_attention ?? counts.attention;

  return (
    <PageShell>
      <section className={s.head}>
        <div className={s.headText}>
          <h1>{greeting()}, {user?.display_name?.split(' ')[0]}</h1>
          {list.length > 0 && (
            <p className={s.summary}>
              <Odometer value={changed} /> of your <Odometer value={total} /> page{total === 1 ? '' : 's'} changed today.{' '}
              {attention > 0 ? <><Odometer value={attention} /> need{attention === 1 ? 's' : ''} attention.</> : 'Nothing needs your attention.'}
            </p>
          )}
        </div>
        <div className={s.movementSlot}>
          <Movement linkToSystem={!!user?.is_admin} />
        </div>
      </section>

      {isLoading ? (
        <ul className={s.grid} aria-busy="true">
          {Array.from({ length: 6 }, (_, i) => (
            <li key={i} className={s.card}><Skeleton width={168} height={168} radius="50%" /><Skeleton width={120} height={18} /></li>
          ))}
        </ul>
      ) : list.length === 0 ? (
        <EmptyDashboard />
      ) : (
        <>
          <div className={s.toolbar}>
            <div className={s.chips} role="group" aria-label="Filter pages">
              <Chip active={filter === 'all'} count={counts.all} onClick={() => setFilter('all')}>All</Chip>
              <Chip active={filter === 'changed'} count={counts.changed} onClick={() => setFilter('changed')}>Changed today</Chip>
              <Chip active={filter === 'attention'} count={counts.attention} onClick={() => setFilter('attention')}>Needs attention</Chip>
              <Chip active={filter === 'paused'} count={counts.paused} onClick={() => setFilter('paused')}>Paused</Chip>
            </div>
            <div className={s.toolsRight}>
              <label className={s.search}>
                <MagnifyingGlass size={16} weight="light" aria-hidden="true" />
                <span className="visually-hidden">Search pages</span>
                <input type="search" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
              </label>
              <SegmentedControl<View> label="View" value={view} onChange={setView}
                options={[{ value: 'dials', label: 'Dials' }, { value: 'list', label: 'List' }]} />
            </div>
          </div>

          {visible.length === 0 ? (
            <p className={s.noMatch}>No pages match. <button type="button" className={s.linkBtn} onClick={() => { setFilter('all'); setQ(''); }}>Show all pages</button></p>
          ) : view === 'dials' ? (
            <ul className={s.grid}>
              {visible.map((w, i) => <DialCard key={w.id} w={w} index={i} onDelete={setToDelete} />)}
            </ul>
          ) : (
            <WatchTable watches={visible} onDelete={setToDelete} now={now} />
          )}
        </>
      )}

      <Modal
        open={!!toDelete}
        onClose={() => setToDelete(null)}
        title={`Stop watching ${toDelete?.name ?? 'this page'}?`}
        actions={
          <>
            <Button variant="ghost" onClick={() => setToDelete(null)}>Keep it</Button>
            <Button variant="danger" loading={del.isPending} onClick={() => toDelete && del.mutate(toDelete.id, {
              onSuccess: () => { toast('Page removed.'); setToDelete(null); },
            })}>Delete page</Button>
          </>
        }
      >
        <p className="muted">Its history, screenshots and alerts will be deleted. This can't be undone.</p>
      </Modal>
    </PageShell>
  );
}
