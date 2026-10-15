/**
 * Picker.tsx — "Pick regions": click parts of the page to watch, to ignore, or to track as a number.
 *
 * The page appears in <iframe sandbox="allow-scripts"> — no allow-same-origin — so the page's content
 * runs in an opaque origin and can't touch our cookies or DOM. We talk to the picker script inside it
 * ONLY with postMessage, and we accept a message only when `event.source === iframe.contentWindow`.
 *
 * Saving calls PUT /selectors, which re-baselines the watch (a "New starting point" version, no alert).
 */
import { ArrowLeft, X } from '@phosphor-icons/react';
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { api, ApiError, API_BASE } from '../api/client';
import { keys, useWatch } from '../api/hooks';
import type { WatchDetail } from '../api/types';
import { useQueryClient } from '@tanstack/react-query';
import { PageShell } from '../components/layout/PageShell';
import { useMedia } from '../lib/useMedia';
import { Button } from '../components/ui/Button';
import { SegmentedControl } from '../components/ui/SegmentedControl';
import { Skeleton } from '../components/ui/misc';
import s from './Picker.module.css';

type Mode = 'watch' | 'ignore' | 'number';

interface TestResult {
  text_preview: string;
  number_preview: string | null;
  missing_selectors: string[];
  available: boolean;
}

export default function Picker() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: watch } = useWatch(id);
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [mode, setMode] = useState<Mode>('watch');
  const [watchSel, setWatchSel] = useState<string[]>([]);
  const [ignoreSel, setIgnoreSel] = useState<string[]>([]);
  const [numberSel, setNumberSel] = useState<string | null>(null);
  const [hovered, setHovered] = useState('');
  const [manual, setManual] = useState('');
  const [test, setTest] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadedFrom, setLoadedFrom] = useState<number | null>(null);
  // Touch screens: a tapped element waits here until the user confirms it (or widens it to its parent).
  const [candidate, setCandidate] = useState<{ selector: string; text: string; atTop: boolean } | null>(null);
  const touch = useMedia('(pointer: coarse)');

  // Start with the watch's saved selections.
  useEffect(() => {
    if (watch && loadedFrom !== watch.id) {
      setWatchSel(watch.watch_selectors);
      setIgnoreSel(watch.ignore_selectors);
      setNumberSel(watch.number_selector ?? null);
      setLoadedFrom(watch.id);
    }
  }, [watch, loadedFrom]);

  // Open a picker session (a signed 10-minute frame URL).
  useEffect(() => {
    api<{ frame_url: string }>(`/api/watches/${id}/picker/session`, { method: 'POST' })
      .then((r) => setFrameUrl(API_BASE + r.frame_url))
      .catch((e) => toast(e instanceof ApiError ? e.message : 'Could not open the picker.'));
  }, [id]);

  const post = useCallback((msg: unknown) => {
    // The frame has an opaque origin, so targetOrigin must be '*'. We only send selectors and a mode.
    frameRef.current?.contentWindow?.postMessage(msg, '*');
  }, []);

  // Messages from the frame.
  useEffect(() => {
    function onMessage(e: MessageEvent) {
      if (!frameRef.current || e.source !== frameRef.current.contentWindow) return; // only our iframe
      const data = e.data as { type?: string; selector?: string | null; textPreview?: string; mode?: Mode; atTop?: boolean };
      if (data.type === 'ready') setReady(true);
      if (data.type === 'candidate') {
        setCandidate(data.selector ? { selector: data.selector, text: data.textPreview ?? '', atTop: !!data.atTop } : null);
        if (data.selector) setHovered(data.selector);
      }
      if (data.type === 'hover' && typeof data.selector === 'string') setHovered(data.selector);
      if (data.type === 'pick' && typeof data.selector === 'string' && data.selector) {
        const sel = data.selector;
        const pickMode = data.mode ?? mode;
        if (pickMode === 'watch') setWatchSel((l) => (l.includes(sel) ? l : [...l, sel]));
        if (pickMode === 'ignore') setIgnoreSel((l) => (l.includes(sel) ? l : [...l, sel]));
        if (pickMode === 'number') setNumberSel(sel);
        setTest(null);
      }
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [mode]);

  // Keep the frame's mode and persistent outlines in sync.
  useEffect(() => { if (ready) post({ type: 'mode', mode }); }, [ready, mode, post]);
  useEffect(() => {
    if (ready) post({ type: 'highlight', selectors: { watch: watchSel, ignore: ignoreSel, number: numberSel ? [numberSel] : [] } });
  }, [ready, watchSel, ignoreSel, numberSel, post]);

  function addManual(e: FormEvent) {
    e.preventDefault();
    const sel = manual.trim();
    if (!sel) return;
    if (mode === 'watch') setWatchSel((l) => [...new Set([...l, sel])]);
    if (mode === 'ignore') setIgnoreSel((l) => [...new Set([...l, sel])]);
    if (mode === 'number') setNumberSel(sel);
    setManual('');
    setTest(null);
  }

  async function runTest() {
    setTesting(true);
    try {
      setTest(await api<TestResult>(`/api/watches/${id}/picker/test`, {
        method: 'POST', body: { watch_selectors: watchSel, ignore_selectors: ignoreSel, number_selector: numberSel },
      }));
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Test failed.');
    } finally {
      setTesting(false);
    }
  }

  async function save() {
    setSaving(true);
    try {
      const w = await api<WatchDetail>(`/api/watches/${id}/selectors`, {
        method: 'PUT', body: { watch_selectors: watchSel, ignore_selectors: ignoreSel, number_selector: numberSel },
      });
      qc.setQueryData(keys.watch(id), w);
      void qc.invalidateQueries({ queryKey: keys.snapshots(id) });
      void qc.invalidateQueries({ queryKey: keys.watches });
      toast('Regions saved. Future checks only look at what you picked.');
      navigate(`/pages/${id}`);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Could not save regions.');
    } finally {
      setSaving(false);
    }
  }

  const list = (title: string, items: string[], remove: (sel: string) => void, cls: string, empty: string) => (
    <div className={s.group}>
      <h3 className={`${s.groupTitle} ${cls}`}>{title}</h3>
      {items.length === 0 ? <p className={s.empty}>{empty}</p> : (
        <ul className={s.sels}>
          {items.map((sel) => (
            <li key={sel} className={s.sel}>
              <code>{sel}</code>
              <button type="button" className={s.remove} aria-label={`Remove ${sel}`} onClick={() => { remove(sel); setTest(null); }}><X size={14} /></button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  return (
    <PageShell>
      <Link to={`/pages/${id}`} className={s.back}><ArrowLeft size={16} /> {watch?.name ?? 'Back'}</Link>
      <div className={s.head}>
        <h1 className={s.title}>Pick regions</h1>
        <div className={s.headTools}>
          <SegmentedControl<Mode> label="Picking mode" value={mode} onChange={setMode}
            options={[{ value: 'watch', label: 'Watch' }, { value: 'ignore', label: 'Ignore' }, { value: 'number', label: 'Number' }]} />
          <Button variant="primary" loading={saving} onClick={save}>Save</Button>
        </div>
      </div>
      <p className={s.lede}>
        {mode === 'watch' && 'Click the parts of the page you care about. Only these are compared.'}
        {mode === 'ignore' && 'Click parts that change but don’t matter, like a live score or a “recommended” box.'}
        {mode === 'number' && 'Click a price or count to chart it over time.'}
      </p>

      <div className={s.layout}>
        <div className={s.frameCol}>
          <div className={`${s.frameWrap} ${s[`mode_${mode}`]}`}>
            {frameUrl ? (
              <iframe ref={frameRef} src={frameUrl} title="Page snapshot for picking regions" className={s.frame}
                sandbox="allow-scripts" referrerPolicy="no-referrer" />
            ) : <Skeleton height="100%" />}
          </div>
          {candidate && (
            <div className={s.candidate} role="group" aria-label="Selected element">
              <div className={s.candidateText}>
                <code>{candidate.selector}</code>
                {candidate.text && <span>{candidate.text}</span>}
                {candidate.atTop && <span>This is already the largest region on the page.</span>}
              </div>
              <div className={s.candidateActions}>
                <Button size="sm" variant="secondary" disabled={candidate.atTop} onClick={() => post({ type: 'parent' })}
                  title={candidate.atTop ? 'This is already the largest region; anything bigger is the whole page.' : undefined}>
                  Select parent
                </Button>
                <Button size="sm" variant="primary" onClick={() => post({ type: 'confirm' })}>
                  {mode === 'watch' ? 'Add to Watching' : mode === 'ignore' ? 'Add to Ignoring' : 'Use as number'}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => post({ type: 'cancel' })}>Cancel</Button>
              </div>
            </div>
          )}
          <p className={s.hint}>
            <span className="mono">{hovered || (touch ? 'Tap an element to select it.' : 'Hover an element to see its selector.')}</span>
            <span>{touch ? 'Tap an element, then use Select parent to widen it.' : 'Arrow up selects the parent element. Enter picks. Esc cancels.'}</span>
          </p>
        </div>

        <aside className={s.panel} aria-label="Picked regions">
          {list('Watching', watchSel, (x) => setWatchSel((l) => l.filter((y) => y !== x)), s.lume, 'The whole page (nothing picked).')}
          {list('Ignoring', ignoreSel, (x) => setIgnoreSel((l) => l.filter((y) => y !== x)), s.ruby, 'Nothing extra. Built-in noise filters still apply.')}
          {list('Number', numberSel ? [numberSel] : [], () => setNumberSel(null), s.blued, 'Not tracking a number.')}

          <form onSubmit={addManual} className={s.manual}>
            <label htmlFor="manual-sel" className={s.manualLabel}>Add a CSS selector to “{mode}”</label>
            <div className={s.manualRow}>
              <input id="manual-sel" className={s.manualInput} value={manual} onChange={(e) => setManual(e.target.value)} placeholder="#news-list" spellCheck={false} />
              <Button type="submit" size="sm" variant="secondary">Add</Button>
            </div>
          </form>

          <div className={s.testBox}>
            <Button variant="secondary" size="sm" loading={testing} onClick={runTest}>Test selection</Button>
            {test && (
              <div className={s.testResult}>
                {test.missing_selectors.length > 0 && <p className={s.missing}>Not found on the page: {test.missing_selectors.join(', ')}</p>}
                {test.number_preview && <p className="small">Number: <strong>{test.number_preview}</strong></p>}
                <pre className={s.preview}>{test.text_preview || '(no text)'}</pre>
              </div>
            )}
          </div>
        </aside>
      </div>
    </PageShell>
  );
}
