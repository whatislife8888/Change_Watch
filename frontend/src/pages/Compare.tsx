/**
 * Compare.tsx — compare ANY two versions of a page (requirement 6). Alert links land here.
 *
 * Two version pickers (every snapshot is listed); the URL (?a=&b=) updates so the view is shareable.
 * Views: Text (unified), Side by side, Screenshot (with the Loupe), Slider and Overlay.
 */
import { ArrowLeft } from '@phosphor-icons/react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useCompare, useMe, useSnapshots, useWatch } from '../api/hooks';
import { SideBySideDiff } from '../components/diff/SideBySideDiff';
import { UnifiedDiff } from '../components/diff/UnifiedDiff';
import { OverlayCompare, ScreenshotDiff, SliderCompare } from '../components/diff/VisualViews';
import { PageShell } from '../components/layout/PageShell';
import { EmptyState, Skeleton } from '../components/ui/misc';
import { Tabs } from '../components/ui/Tabs';
import { dayAndTime } from '../lib/time';
import s from './Compare.module.css';

type View = 'text' | 'sbs' | 'shot' | 'slider' | 'overlay';

export default function Compare() {
  const id = Number(useParams().id);
  const [params, setParams] = useSearchParams();
  const { data: me } = useMe();
  const { data: watch } = useWatch(id);
  const { data: snaps } = useSnapshots(id);
  const [view, setView] = useState<View>((params.get('view') as View) || 'text');
  const tz = me?.timezone;

  // Default to "previous vs latest" when no versions are in the URL.
  const a = Number(params.get('a')) || (snaps && snaps.length > 1 ? snaps[1].id : null);
  const b = Number(params.get('b')) || (snaps && snaps.length > 0 ? snaps[0].id : null);
  const { data, isLoading, error } = useCompare(id, a, b);

  useEffect(() => {
    if (!params.get('a') && a && b) setParams({ a: String(a), b: String(b), view }, { replace: true });
  }, [a, b, params, setParams, view]);

  const label = (sid: number | null) => {
    const snap = snaps?.find((x) => x.id === sid);
    return snap ? dayAndTime(snap.created_at, tz) : '';
  };
  const labels: [string, string] = [label(a), label(b)];

  const options = useMemo(() => (snaps ?? []).map((x) => (
    <option key={x.id} value={x.id}>{dayAndTime(x.created_at, tz)}{x.is_baseline ? ' (new starting point)' : ''}</option>
  )), [snaps, tz]);

  const setVersion = (key: 'a' | 'b', value: string) => setParams((p) => { p.set(key, value); return p; }, { replace: true });
  const changeView = (v: View) => { setView(v); setParams((p) => { p.set('view', v); return p; }, { replace: true }); };

  const stats = data?.text.stats;
  const summary = data?.b.summary;

  return (
    <PageShell>
      <Link to={`/pages/${id}`} className={s.back}><ArrowLeft size={16} /> {watch?.name ?? 'Back'}</Link>
      <header className={s.head}>
        <h1 className={s.title}>Compare versions</h1>
        <div className={s.pickers}>
          <label className={s.picker}>
            <span>Compare</span>
            <select value={a ?? ''} onChange={(e) => setVersion('a', e.target.value)} aria-label="Older version">{options}</select>
          </label>
          <label className={s.picker}>
            <span>with</span>
            <select value={b ?? ''} onChange={(e) => setVersion('b', e.target.value)} aria-label="Newer version">{options}</select>
          </label>
        </div>
        {data && (
          <p className={s.summary}>
            {summary && <span className={s.summaryLine}>{summary}</span>}
            <span className="num">
              {stats!.added + stats!.changed} line{stats!.added + stats!.changed === 1 ? '' : 's'} added, {stats!.removed + stats!.changed} removed.
              {data.visual.available ? ` ${data.visual.changed_percent.toFixed(1)}% of the page looks different.` : ''}
            </span>
          </p>
        )}
      </header>

      {snaps && snaps.length < 2 ? (
        <EmptyState title="Only one version so far." body="We save a new version each time the page really changes. Come back after the next change, or use Check now." />
      ) : (
        <>
          <Tabs<View>
            label="Comparison view"
            value={view}
            onChange={changeView}
            tabs={[
              { value: 'text', label: 'Text' },
              { value: 'sbs', label: 'Side by side' },
              { value: 'shot', label: 'Screenshot' },
              { value: 'slider', label: 'Slider' },
              { value: 'overlay', label: 'Overlay' },
            ]}
          />
          <div className={s.panel}>
            {a === b ? <p className="muted">Pick two different versions.</p> : null}
            {isLoading && <div className={s.loading}><Skeleton height={28} /><Skeleton height={28} /><Skeleton height={28} width="70%" /></div>}
            {error && <p className={s.error}>{error instanceof ApiError ? error.message : 'Could not load the comparison.'}</p>}
            {data && view === 'text' && <UnifiedDiff ops={data.text.ops} />}
            {data && view === 'sbs' && <SideBySideDiff ops={data.text.ops} labels={labels} />}
            {data && (view === 'shot' || view === 'slider' || view === 'overlay') && !data.visual.available && (
              <p className="muted">Screenshots for one of these versions aren't available.</p>
            )}
            {data && data.visual.available && view === 'shot' && <ScreenshotDiff visual={data.visual} />}
            {data && data.visual.available && view === 'slider' && <SliderCompare visual={data.visual} labels={labels} />}
            {data && data.visual.available && view === 'overlay' && <OverlayCompare visual={data.visual} />}
          </div>
        </>
      )}
    </PageShell>
  );
}
