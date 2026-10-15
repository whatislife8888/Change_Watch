/**
 * ImportTemplate.tsx — /import/:token: add a page from someone's shared setup (same regions, ignore
 * rules and keywords; your own alert settings).
 */
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { api, ApiError } from '../api/client';
import type { Template, WatchDetail } from '../api/types';
import { Dial } from '../components/dial/Dial';
import { PageShell } from '../components/layout/PageShell';
import { Button, ButtonLink } from '../components/ui/Button';
import { EmptyState, Skeleton } from '../components/ui/misc';
import { intervalLabel } from '../lib/time';
import { useState } from 'react';
import s from './ImportTemplate.module.css';

export default function ImportTemplate() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const { data, isLoading, error } = useQuery({ queryKey: ['template', token], queryFn: () => api<Template>(`/api/templates/${token}`) });

  async function add() {
    setBusy(true);
    try {
      const w = await api<WatchDetail>(`/api/templates/${token}/import`, { method: 'POST' });
      toast('Page added. First check running.');
      navigate(`/pages/${w.id}`);
    } catch (e) {
      if (e instanceof ApiError && e.code === 'already_watching') {
        toast("You're already watching this page.");
        navigate(`/pages/${e.extra.watch_id as number}`);
      } else toast(e instanceof ApiError ? e.message : 'Could not add the page.');
    } finally {
      setBusy(false);
    }
  }

  if (isLoading) return <PageShell><Skeleton width={320} height={320} radius="50%" /></PageShell>;
  if (error || !data) return <PageShell><EmptyState title="This shared setup doesn't exist." body="The link may be mistyped."><ButtonLink to="/">Back to your pages</ButtonLink></EmptyState></PageShell>;
  const c = data.config;
  return (
    <PageShell>
      <div className={s.layout}>
        <Dial seed={data.dial_seed} size={320} engrave decorative status="pending" showDate={false} />
        <div className={s.info}>
          <h1 className={s.title}>{c.name}</h1>
          <p className="muted">{data.owner_name} shared their setup for <strong>{data.domain}</strong>.</p>
          <dl className={s.list}>
            <div><dt>Address</dt><dd>{c.url}</dd></div>
            <div><dt>Checks</dt><dd>{intervalLabel(c.interval_minutes)}, {c.sensitivity} sensitivity</dd></div>
            <div><dt>Watching</dt><dd>{c.watch_selectors.length ? c.watch_selectors.join(', ') : 'The whole page'}</dd></div>
            <div><dt>Ignoring</dt><dd>{c.ignore_selectors.length ? c.ignore_selectors.join(', ') : 'Only the built-in noise'}</dd></div>
            {c.keyword_mode !== 'off' && <div><dt>Keywords</dt><dd>{c.keywords.join(', ')} ({c.keyword_mode})</dd></div>}
          </dl>
          <p className="muted small">Your own alert settings apply. Nothing about the person who shared it is copied.</p>
          <div><Button variant="primary" loading={busy} onClick={add}>Add this page</Button></div>
        </div>
      </div>
    </PageShell>
  );
}
