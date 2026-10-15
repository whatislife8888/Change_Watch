/**
 * System.tsx — the engine, explained (admin only): the large Movement plus plain-sentence statistics —
 * how many fetches sharing saved, how checks turned out in the last 24 hours, render speed, the queue,
 * when each website may next be contacted (politeness), and how many noise rules were learned.
 */
import { useMe, useAdminStats } from '../api/hooks';
import { PageShell } from '../components/layout/PageShell';
import { Movement } from '../components/movement/Movement';
import { EmptyState, Skeleton } from '../components/ui/misc';
import { relative } from '../lib/time';
import { useNow } from '../lib/useNow';
import s from './System.module.css';

const pct = (v: number) => `${Math.round(v * 100)}%`;

export default function System() {
  const { data: me } = useMe();
  const { data, isLoading } = useAdminStats(!!me?.is_admin);
  const now = useNow(5000);

  if (me && !me.is_admin) {
    return <PageShell><EmptyState title="Only the administrator can see this." body="The system view shows the whole engine, so it's limited to the first account (or ADMIN_EMAIL)." /></PageShell>;
  }

  return (
    <PageShell>
      <h1>System</h1>
      <p className={s.lede}>What the engine is doing right now, in plain words.</p>
      <div className={s.layout}>
        <div className={s.movement}><Movement size="lg" /></div>
        {isLoading || !data ? (
          <div className={s.facts}><Skeleton height={32} /><Skeleton height={32} /><Skeleton height={32} /></div>
        ) : (
          <div className={s.facts}>
            <section className={s.block}>
              <h2 className={s.h2}>Sharing</h2>
              <p>
                <strong className="num">{data.watches}</strong> watches point at <strong className="num">{data.targets}</strong> distinct pages,
                a sharing ratio of <strong className="num">{data.sharing_ratio.toFixed(2)}</strong>. Each page is fetched once per cycle for everyone who watches it.
              </p>
              {data.renders_saved_24h > 0 && <p className="muted">That saved about {data.renders_saved_24h} browser renders in the last 24 hours.</p>}
              {data.top_shared.length > 0 && (
                <ul className={s.list}>
                  {data.top_shared.map((t) => <li key={String(t.url)}><span>{String(t.domain)}</span><span className="num">{String(t.watchers)} watchers</span></li>)}
                </ul>
              )}
            </section>
            <section className={s.block}>
              <h2 className={s.h2}>Checks in the last 24 hours</h2>
              <p>
                <strong className="num">{data.checks_24h}</strong> page evaluations: <strong>{pct(data.ok_rate)}</strong> reached the page,
                {' '}<strong>{pct(data.error_rate)}</strong> couldn't, and <strong>{pct(data.blocked_rate)}</strong> were blocked or disallowed.
              </p>
              <ul className={s.list}>
                {Object.entries(data.outcome_counts).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                  <li key={k}><span>{k.replace(/_/g, ' ')}</span><span className="num">{v}</span></li>
                ))}
              </ul>
              {data.avg_render_ms !== null && <p className="muted">A full browser render takes {(data.avg_render_ms / 1000).toFixed(1)} seconds on average.</p>}
            </section>
            <section className={s.block}>
              <h2 className={s.h2}>Queue and workers</h2>
              <p>
                {String(data.queue.running)} running, {String(data.queue.waiting)} waiting, {String(data.queue.workers)} workers.
                {' '}{String(data.queue.completed)} jobs finished since the server started.
              </p>
            </section>
            <section className={s.block}>
              <h2 className={s.h2}>Politeness</h2>
              <p className="muted">One request at a time per website, at least 10 seconds apart (longer if robots.txt asks).</p>
              {data.domains.length === 0 ? <p>No websites contacted yet.</p> : (
                <ul className={s.list}>
                  {data.domains.map((d) => (
                    <li key={d.domain}>
                      <span>{d.domain}</span>
                      <span className="num">{d.busy ? 'fetching now' : d.next_allowed_at && Date.parse(d.next_allowed_at) > now ? `next request ${relative(d.next_allowed_at, now)}` : 'ready'}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className={s.block}>
              <h2 className={s.h2}>Learned noise</h2>
              <p><strong className="num">{data.learned_rules}</strong> rules learned from pages that differ on every load.</p>
              <p className="muted">{data.users} account{data.users === 1 ? '' : 's'} in total.</p>
            </section>
          </div>
        )}
      </div>
    </PageShell>
  );
}
