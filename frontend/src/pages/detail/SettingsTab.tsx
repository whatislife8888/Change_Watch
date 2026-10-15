/**
 * SettingsTab.tsx — everything about one watch: name, interval, sensitivity, keywords, number tracking,
 * alert channels, carousel handling, learned noise rules (removable), built-in filters (read-only),
 * RSS link, sharing, pause and delete.
 */
import { Copy, X } from '@phosphor-icons/react';
import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ApiError } from '../../api/client';
import { useDeleteRule, useDeleteWatch, useRegenerateRss, useShare, useUpdateWatch } from '../../api/hooks';
import type { KeywordMode, Sensitivity, WatchDetail } from '../../api/types';
import { IntervalField, KeywordFields, SensitivityField } from '../../components/forms/WatchFields';
import { Button } from '../../components/ui/Button';
import { Checkbox, Input, Switch } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { formatKeywords, parseKeywords } from '../../lib/keywords';
import { relative } from '../../lib/time';
import s from './Detail.module.css';

async function copy(text: string, what: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast(`${what} copied.`);
  } catch {
    toast(`Couldn't copy. Select the ${what.toLowerCase()} and copy it manually.`);
  }
}

function numOrNull(v: string): number | null {
  if (!v.trim()) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function SettingsTab({ watch }: { watch: WatchDetail }) {
  const update = useUpdateWatch(watch.id);
  const delRule = useDeleteRule(watch.id);
  const del = useDeleteWatch();
  const rss = useRegenerateRss(watch.id);
  const share = useShare(watch.id);
  const navigate = useNavigate();

  const [name, setName] = useState(watch.name);
  const [interval, setInterval] = useState(watch.interval_minutes);
  const [sensitivity, setSensitivity] = useState<Sensitivity>(watch.sensitivity);
  const [kwText, setKwText] = useState(formatKeywords(watch.keywords));
  const [kwMode, setKwMode] = useState<KeywordMode>(watch.keyword_mode);
  const [numSel, setNumSel] = useState(watch.number_selector ?? '');
  const [numRe, setNumRe] = useState(watch.number_regex ?? '');
  const [below, setBelow] = useState(watch.number_thresholds.below?.toString() ?? '');
  const [above, setAbove] = useState(watch.number_thresholds.above?.toString() ?? '');
  const [pct, setPct] = useState(watch.number_thresholds.change_pct?.toString() ?? '');
  const [alerts, setAlerts] = useState({ email: watch.alert_email, telegram: watch.alert_telegram, discord: watch.alert_discord });
  const [carousels, setCarousels] = useState(watch.ignore_carousels);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);

  useEffect(() => { setName(watch.name); }, [watch.name]);

  function save(e: FormEvent) {
    e.preventDefault();
    update.mutate({
      name, interval_minutes: interval, sensitivity,
      keywords: parseKeywords(kwText), keyword_mode: kwMode,
      number_selector: numSel.trim() || null, number_regex: numRe.trim() || null,
      number_thresholds: { below: numOrNull(below), above: numOrNull(above), change_pct: numOrNull(pct) },
      alert_email: alerts.email, alert_telegram: alerts.telegram, alert_discord: alerts.discord,
      ignore_carousels: carousels,
    }, {
      onSuccess: () => toast('Settings saved.'),
      onError: (err) => toast(err instanceof ApiError ? err.message : 'Could not save.'),
    });
  }

  return (
    <div className={s.settings}>
      <form onSubmit={save} className={s.section}>
        <h2 className={s.sectionTitle}>Checking</h2>
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
        <IntervalField value={interval} onChange={setInterval} />
        <SensitivityField value={sensitivity} onChange={setSensitivity} />
        <KeywordFields text={kwText} mode={kwMode} onText={setKwText} onMode={setKwMode} />
        <Switch
          label="Ignore rotating banners and carousels"
          hint="Turn off if the carousel is what you want to watch."
          checked={carousels}
          onChange={(e) => setCarousels(e.target.checked)}
        />

        <h2 className={s.sectionTitle}>Track a number</h2>
        <p className="muted small">Record a price or count on every check and chart it. Pick it visually in Pick regions, or type a selector.</p>
        <div className={s.twoCol}>
          <Input label="CSS selector" value={numSel} onChange={(e) => setNumSel(e.target.value)} placeholder=".price" spellCheck={false} />
          <Input label="Or a pattern (regex)" value={numRe} onChange={(e) => setNumRe(e.target.value)} placeholder="Price: ₹([\d,]+)" spellCheck={false}
            hint="One group in brackets captures the number." />
        </div>
        <div className={s.threeCol}>
          <Input label="Alert below" inputMode="decimal" value={below} onChange={(e) => setBelow(e.target.value)} placeholder="70000" />
          <Input label="Alert above" inputMode="decimal" value={above} onChange={(e) => setAbove(e.target.value)} />
          <Input label="Alert on change of %" inputMode="decimal" value={pct} onChange={(e) => setPct(e.target.value)} placeholder="5" />
        </div>

        <h2 className={s.sectionTitle}>Alerts</h2>
        <div className={s.stack}>
          <Checkbox label="Email" checked={alerts.email} onChange={(e) => setAlerts({ ...alerts, email: e.target.checked })} />
          <Checkbox label="Telegram" checked={alerts.telegram} onChange={(e) => setAlerts({ ...alerts, telegram: e.target.checked })} />
          <Checkbox label="Discord" checked={alerts.discord} onChange={(e) => setAlerts({ ...alerts, discord: e.target.checked })} />
          <p className="muted small">Channel details and the daily digest live in Settings.</p>
        </div>
        <div><Button type="submit" variant="primary" loading={update.isPending}>Save settings</Button></div>
      </form>

      <section className={s.section}>
        <h2 className={s.sectionTitle}>Learned noise rules</h2>
        <p className="muted small">
          When a page differs between two loads 10 seconds apart, those parts are noise. We learn them so they never alert you.
          Rules belong to the page, so removing one affects everyone who watches it.
        </p>
        {watch.volatile_rules.length === 0 ? (
          <p className="small">Nothing learned yet.</p>
        ) : (
          <ul className={s.rules}>
            {watch.volatile_rules.map((r, i) => (
              <li key={`${r.kind}-${r.value}`} className={s.rule}>
                <div className={s.ruleText}>
                  <span className={s.ruleKind}>{r.kind === 'selector' ? 'Element' : 'Line pattern'}</span>
                  <code className={s.ruleValue}>{r.value}</code>
                  {r.sample && r.sample !== r.value && <span className={s.ruleSample}>e.g. {r.sample}</span>}
                  <span className={s.ruleSample}>Learned {relative(r.learned_at)}{r.hits ? `, used ${r.hits} times` : ''}</span>
                </div>
                <Button size="sm" variant="ghost" iconOnly aria-label={`Remove rule ${r.value}`} onClick={() => delRule.mutate(i)}><X size={16} /></Button>
              </li>
            ))}
          </ul>
        )}
        <details className={s.details}>
          <summary>Built-in noise filters (always on)</summary>
          <p className="muted small">Timestamps, dates near today, relative times, countdowns, view and like counters, random tokens and copyright years are normalised before comparing. These page parts are removed:</p>
          {Object.entries(watch.builtin_noise_selectors).map(([group, sels]) => (
            <div key={group} className={s.builtinGroup}>
              <span className="small">{group}</span>
              <code className={s.builtinCode}>{sels.join(', ')}</code>
            </div>
          ))}
        </details>
      </section>

      <section className={s.section}>
        <h2 className={s.sectionTitle}>RSS and sharing</h2>
        <div className={s.copyRow}>
          <Input label="RSS feed" readOnly value={watch.rss_url} onFocus={(e) => e.currentTarget.select()} />
          <Button size="sm" variant="secondary" onClick={() => copy(watch.rss_url, 'Feed link')}><Copy size={16} /> Copy</Button>
        </div>
        <div><Button size="sm" variant="ghost" loading={rss.isPending} onClick={() => rss.mutate(undefined, { onSuccess: () => toast('New feed link created. The old one stopped working.') })}>Create a new feed link</Button></div>
        <p className="muted small">Share setup creates a link that lets someone add this page with the same regions, ignore rules and keywords. Your alert settings are never shared.</p>
        <div className={s.copyRow}>
          {shareUrl && <Input label="Share link" readOnly value={shareUrl} onFocus={(e) => e.currentTarget.select()} />}
          <Button size="sm" variant="secondary" loading={share.isPending} onClick={() => share.mutate(undefined, {
            onSuccess: (r) => { setShareUrl(r.template_url); void copy(r.template_url, 'Share link'); },
          })}>{shareUrl ? 'Copy again' : 'Share setup'}</Button>
        </div>
      </section>

      <section className={s.section}>
        <h2 className={s.sectionTitle}>Pause or delete</h2>
        <div className={s.actionsRow}>
          <Button variant="secondary" onClick={() => update.mutate({ paused: !watch.paused }, { onSuccess: () => toast(watch.paused ? 'Checks resumed.' : 'Paused. No checks until you resume.') })}>
            {watch.paused ? 'Resume checks' : 'Pause checks'}
          </Button>
          <Button variant="danger" onClick={() => setConfirmDelete(true)}>Delete page</Button>
        </div>
      </section>

      <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title={`Stop watching ${watch.name}?`}
        actions={<>
          <Button variant="ghost" onClick={() => setConfirmDelete(false)}>Keep it</Button>
          <Button variant="danger" loading={del.isPending} onClick={() => del.mutate(watch.id, { onSuccess: () => { toast('Page removed.'); navigate('/'); } })}>Delete page</Button>
        </>}>
        <p className="muted">Its history, screenshots and alerts will be deleted. This can't be undone.</p>
      </Modal>
    </div>
  );
}
