/**
 * AddPage.tsx — "Add page": the form on the left, a live dial on the right that changes as you type.
 *
 * As the URL changes we call /api/url/preview (debounced 250 ms, previous request cancelled). It returns
 * the normalised URL, domain and dial seed, so the user sees exactly what will be watched — and the dial
 * cross-fades to that page's own pattern. It also tells you if others already watch the page.
 * Submit → POST /api/watches → navigate to the page's detail screen while the first check runs.
 */
import { CaretDown } from '@phosphor-icons/react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ApiError } from '../api/client';
import { previewUrl, useCreateWatch } from '../api/hooks';
import type { KeywordMode, Sensitivity, UrlPreview } from '../api/types';
import { Dial } from '../components/dial/Dial';
import { IntervalField, KeywordFields, SensitivityField } from '../components/forms/WatchFields';
import { PageShell } from '../components/layout/PageShell';
import { Button } from '../components/ui/Button';
import { Checkbox, Input } from '../components/ui/Input';
import { parseKeywords } from '../lib/keywords';
import { intervalLabel } from '../lib/time';
import s from './AddPage.module.css';

const IDLE_SEED = 'a11ce5ed';

/** Debounced URL preview. Returns the latest preview (or null) and whether a request is in flight. */
export function useUrlPreview(url: string) {
  const [preview, setPreview] = useState<UrlPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const ctrl = useRef<AbortController | null>(null);
  useEffect(() => {
    if (!url.trim()) {
      setPreview(null);
      return;
    }
    const timer = window.setTimeout(() => {
      ctrl.current?.abort();
      const c = new AbortController();
      ctrl.current = c;
      setLoading(true);
      previewUrl(url, c.signal)
        .then((p) => setPreview(p))
        .catch(() => { /* aborted or offline: keep the last preview */ })
        .finally(() => { if (ctrl.current === c) setLoading(false); });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [url]);
  return { preview, loading };
}

export default function AddPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const create = useCreateWatch();
  const [url, setUrl] = useState(params.get('url') ?? '');
  const [name, setName] = useState('');
  const [interval, setInterval] = useState(60);
  const [sensitivity, setSensitivity] = useState<Sensitivity>('medium');
  const [more, setMore] = useState(false);
  const [kwText, setKwText] = useState('');
  const [kwMode, setKwMode] = useState<KeywordMode>('off');
  const [alertEmail, setAlertEmail] = useState(true);
  const [alertTelegram, setAlertTelegram] = useState(false);
  const [alertDiscord, setAlertDiscord] = useState(false);
  const [touched, setTouched] = useState(false);
  const { preview } = useUrlPreview(url);

  const urlError = touched && preview && !preview.valid ? preview.error : undefined;
  const serverError = create.error instanceof ApiError ? create.error : null;
  const already = serverError?.code === 'already_watching' ? (serverError.extra.watch_id as number | undefined) : preview?.already_watching_id;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!url.trim()) return;
    create.mutate({
      url, name, interval_minutes: interval, sensitivity,
      keywords: kwMode === 'off' ? [] : parseKeywords(kwText), keyword_mode: kwMode,
      alert_email: alertEmail, alert_telegram: alertTelegram, alert_discord: alertDiscord,
    }, {
      onSuccess: (w) => {
        toast('Page added. First check running.');
        navigate(`/pages/${w.id}`);
      },
    });
  }

  const seed = preview?.valid && preview.dial_seed ? preview.dial_seed : IDLE_SEED;

  return (
    <PageShell>
      <div className={s.layout}>
        <form className={s.form} onSubmit={onSubmit} noValidate>
          <div>
            <h1>Add page</h1>
            <p className={s.lede}>Paste the address of a public page. We'll check it {intervalLabel(interval)} and tell you when something real changes.</p>
          </div>

          <div className={s.fields}>
            <Input
              label="Page address"
              placeholder="https://example.com/news"
              value={url}
              autoFocus={!url}
              inputMode="url"
              autoComplete="url"
              spellCheck={false}
              onChange={(e) => setUrl(e.target.value)}
              onBlur={() => setTouched(true)}
              error={urlError ?? (serverError && serverError.code !== 'already_watching' && serverError.code !== 'interval_out_of_range' ? serverError.message : undefined)}
              hint={preview?.valid ? <>We'll watch <span className={s.norm}>{preview.normalised_url}</span>{preview.other_watchers ? <>. {preview.other_watchers} other {preview.other_watchers === 1 ? 'person watches' : 'people watch'} this page, so it's fetched once for everyone.</> : null}</> : 'Only public pages. No logins or passwords.'}
            />
            {already ? (
              <p className={s.notice}>You're already watching this page. <Link to={`/pages/${already}`}>Open it</Link></p>
            ) : null}
            <Input label="Name (optional)" placeholder="We'll use the page title" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
            <IntervalField value={interval} onChange={setInterval} />
            {serverError?.code === 'interval_out_of_range' && <p className={s.error}>{serverError.message}</p>}
            <SensitivityField value={sensitivity} onChange={setSensitivity} />

            <div className={s.more}>
              <button type="button" className={s.moreBtn} aria-expanded={more} onClick={() => setMore((m) => !m)}>
                More options
                <CaretDown size={14} weight="regular" style={{ transform: more ? 'rotate(180deg)' : undefined, transition: 'transform 280ms var(--ease-out)' }} />
              </button>
              {more && (
                <div className={s.moreBody}>
                  <KeywordFields text={kwText} mode={kwMode} onText={setKwText} onMode={setKwMode} />
                  <fieldset className={s.alerts}>
                    <legend>Send alerts by</legend>
                    <Checkbox label="Email" checked={alertEmail} onChange={(e) => setAlertEmail(e.target.checked)} />
                    <Checkbox label="Telegram" hint="Set your chat id in Settings." checked={alertTelegram} onChange={(e) => setAlertTelegram(e.target.checked)} />
                    <Checkbox label="Discord" hint="Set your webhook in Settings." checked={alertDiscord} onChange={(e) => setAlertDiscord(e.target.checked)} />
                  </fieldset>
                </div>
              )}
            </div>
          </div>

          <div className={s.actions}>
            <Button type="submit" variant="primary" loading={create.isPending} disabled={!url.trim()}>Add page</Button>
            <Button variant="ghost" onClick={() => navigate(-1)}>Cancel</Button>
          </div>
        </form>

        <aside className={s.preview} aria-label="Dial preview">
          <Dial seed={seed} size={400} crossfade decorative status="pending" showDate={false} interactive />
          <p className={s.previewCaption}>
            {preview?.valid ? <>The dial for <strong>{preview.domain}</strong>, engraved from its address.</> : 'Every page gets its own dial, engraved from its address.'}
          </p>
        </aside>
      </div>
    </PageShell>
  );
}
