/**
 * PageDetail.tsx — one watched page: a large dial, plain-language status, actions, and four tabs:
 * History (version timeline), Numbers (tracked value chart), Activity (check log), Settings.
 *
 * The large dial shares `layoutId="dial-{id}"` with the dashboard dial, so clicking a dial on the
 * dashboard visually grows it into this page (Motion shared-element transition).
 */
import { ArrowLeft, ArrowSquareOut, DotsThreeVertical } from '@phosphor-icons/react';
import { useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ApiError } from '../api/client';
import { useCheckNow, useMe, useSnapshots, useUpdateWatch, useWatch } from '../api/hooks';
import { Dial } from '../components/dial/Dial';
import { PageShell } from '../components/layout/PageShell';
import { Timeline } from '../components/timeline/Timeline';
import { Button, ButtonLink } from '../components/ui/Button';
import { Menu } from '../components/ui/Menu';
import { EmptyState, Skeleton, StatusText, Tooltip } from '../components/ui/misc';
import { Tabs } from '../components/ui/Tabs';
import { clock, exact, intervalLabel, relative } from '../lib/time';
import { useNow } from '../lib/useNow';
import { jewelFor, statusKindFor } from '../lib/watchStatus';
import { useEngraveKey } from '../realtime/useEvents';
import { ActivityTab } from './detail/ActivityTab';
import { NumbersTab } from './detail/NumbersTab';
import { SettingsTab } from './detail/SettingsTab';
import s from './PageDetail.module.css';

type Tab = 'history' | 'numbers' | 'activity' | 'settings';

function formatNumber(v: number | null | undefined): string | null {
  if (v === null || v === undefined) return null;
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(v);
}

export default function PageDetail() {
  const { id: idParam } = useParams();
  const id = Number(idParam);
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { data: me } = useMe();
  const { data: watch, isLoading, error } = useWatch(id);
  const { data: snapshots } = useSnapshots(id);
  const checkNow = useCheckNow();
  const update = useUpdateWatch(id);
  const engraveKey = useEngraveKey(id);
  const now = useNow(15_000);
  const tab = (params.get('tab') as Tab) || 'history';
  const setTab = (t: Tab) => setParams((p) => { p.set('tab', t); return p; }, { replace: true });
  const [checking, setChecking] = useState(false);
  const tz = me?.timezone;

  if (isLoading) {
    return <PageShell><div className={s.header}><Skeleton width={400} height={400} radius="50%" /><div className={s.info}><Skeleton width={300} height={48} /><Skeleton width={240} height={20} /></div></div></PageShell>;
  }
  if (error || !watch) {
    return <PageShell><EmptyState title="We couldn't find that page." body={error instanceof ApiError ? error.message : undefined}><ButtonLink to="/">Back to your pages</ButtonLink></EmptyState></PageShell>;
  }

  const others = watch.shared_watchers - 1;
  const hasNumber = !!(watch.number_selector || watch.number_regex);
  const flapping = watch.flapping_until && Date.parse(watch.flapping_until) > now;
  const latest = snapshots?.[0];
  const previous = snapshots?.[1];

  const onCheck = () => {
    setChecking(true);
    checkNow.mutate(watch.id, {
      onSuccess: (r) => toast(r.attached ? 'Already in the queue. It will run shortly.' : 'Check queued. Watch the dial.'),
      onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not queue the check.'),
      onSettled: () => setChecking(false),
    });
  };

  return (
    <PageShell>
      <Link to="/" className={s.back}><ArrowLeft size={16} /> All pages</Link>
      <section className={s.header}>
        <div className={s.dialWrap}>
          <Dial
            seed={watch.dial_seed}
            size={420}
            status={jewelFor(watch)}
            paused={watch.paused}
            running={watch.is_running}
            name={watch.name}
            lastCheckedAt={watch.last_checked_at}
            lastChangedAt={watch.last_changed_at}
            nextDueAt={watch.next_due_at}
            intervalMinutes={watch.interval_minutes}
            subValue={hasNumber ? formatNumber(watch.number_latest) : null}
            engraveKey={engraveKey}
            interactive
            layoutId={`dial-${watch.id}`}
          />
        </div>
        <div className={s.info}>
          <h1 className={s.title}>{watch.name}</h1>
          <a href={watch.url} target="_blank" rel="noreferrer noopener" className={s.url}>
            {watch.url.replace(/^https?:\/\//, '')} <ArrowSquareOut size={14} aria-hidden="true" /><span className="visually-hidden">(opens in a new tab)</span>
          </a>
          <div className={s.statusRow}><StatusText status={statusKindFor(watch)} /></div>
          <p className={s.facts}>
            <Tooltip tip={exact(watch.last_checked_at, tz)}><span>{watch.last_checked_at ? `Checked ${relative(watch.last_checked_at, now)}.` : 'Not checked yet.'}</span></Tooltip>{' '}
            <Tooltip tip={exact(watch.last_changed_at, tz)}><span>{watch.last_changed_at ? `Changed ${relative(watch.last_changed_at, now)}.` : 'No changes yet.'}</span></Tooltip>
            <br />
            {watch.paused ? 'Paused. No checks until you resume.' : watch.is_running ? 'Checking now.' : `Next check ${relative(watch.next_due_at, now)}, ${intervalLabel(watch.interval_minutes)}.`}
          </p>
          {watch.status_message && watch.status !== 'ok' && (
            <p className={s.problem} role="status">
              {watch.status_message}
              {watch.next_due_at && !watch.paused ? ` Next try at ${clock(watch.next_due_at, tz)}.` : ''}
            </p>
          )}
          {flapping && (
            <p className={s.notice}>This page is changing a lot, so we've raised its sensitivity until tomorrow.</p>
          )}
          <p className={s.shared}>
            {others > 0
              ? `${others} other ${others === 1 ? 'person watches' : 'people watch'} this page too, so it's fetched once for everyone.`
              : 'Only you watch this page.'}
          </p>
          <div className={s.actions}>
            <Button variant="primary" onClick={onCheck} loading={checking} disabled={watch.paused}>Check now</Button>
            <ButtonLink to={`/pages/${watch.id}/picker`} variant="secondary">Pick regions</ButtonLink>
            <ButtonLink
              to={latest && previous ? `/pages/${watch.id}/compare?a=${previous.id}&b=${latest.id}` : `/pages/${watch.id}/compare`}
              variant="secondary"
              aria-disabled={!previous}
              onClick={(e) => { if (!previous) { e.preventDefault(); toast('Compare needs at least two versions. We save one each time the page changes.'); } }}
            >Compare versions</ButtonLink>
            <Menu
              label="More actions"
              triggerClassName={s.moreBtn}
              trigger={<DotsThreeVertical size={20} weight="bold" />}
              items={[
                { label: watch.paused ? 'Resume checks' : 'Pause checks', onSelect: () => update.mutate({ paused: !watch.paused }) },
                { label: 'Settings', onSelect: () => setTab('settings') },
                { label: 'RSS feed', onSelect: () => window.open(watch.rss_url, '_blank', 'noopener') },
                { label: 'Activity across pages', onSelect: () => navigate('/activity') },
              ]}
            />
          </div>
        </div>
      </section>

      <Tabs<Tab>
        label="Page sections"
        value={tab}
        onChange={setTab}
        tabs={[
          { value: 'history', label: `History${snapshots ? ` (${snapshots.length})` : ''}` },
          { value: 'numbers', label: 'Numbers' },
          { value: 'activity', label: 'Activity' },
          { value: 'settings', label: 'Settings' },
        ]}
      />
      <div className={s.panel} role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === 'history' && (
          snapshots && snapshots.length > 0
            ? <Timeline watchId={watch.id} items={snapshots} timeZone={tz} />
            : <p className="muted">The first version appears here a few seconds after the first check.</p>
        )}
        {tab === 'numbers' && <NumbersTab watch={watch} timeZone={tz} />}
        {tab === 'activity' && <ActivityTab watchId={watch.id} timeZone={tz} />}
        {tab === 'settings' && <SettingsTab key={watch.id} watch={watch} />}
      </div>
    </PageShell>
  );
}
