/**
 * Timeline.tsx — the per-page version history (requirement 8).
 *
 * A vertical blued-steel hairline; each version is a tiny blued screw head (the newest carries a lume
 * dot). Each row: when, the one-line summary (AI summaries get a small sparkle), +added / −removed,
 * a thumbnail, "Compare with previous", and a checkbox so ANY two versions can be compared.
 */
import { Sparkle } from '@phosphor-icons/react';
import clsx from 'clsx';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { mediaUrl } from '../../api/client';
import type { SnapshotItem } from '../../api/types';
import { dayAndTime, exact } from '../../lib/time';
import { Button } from '../ui/Button';
import { Tooltip } from '../ui/misc';
import s from './Timeline.module.css';

export function Timeline({ watchId, items, timeZone }: { watchId: number; items: SnapshotItem[]; timeZone?: string }) {
  const navigate = useNavigate();
  const [picked, setPicked] = useState<number[]>([]);

  const toggle = (id: number) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id].slice(-2)));

  const compareSelected = () => {
    const [x, y] = [...picked].sort((a, b) => a - b);
    navigate(`/pages/${watchId}/compare?a=${x}&b=${y}`);
  };

  return (
    <div className={s.wrap}>
      <div className={s.bar} aria-live="polite">
        <span className="muted small">
          {picked.length === 0 ? 'Tick any two versions to compare them.' : picked.length === 1 ? 'Pick one more version.' : 'Ready to compare.'}
        </span>
        <Button size="sm" variant="secondary" disabled={picked.length !== 2} onClick={compareSelected}>Compare selected</Button>
      </div>
      <ol className={s.list}>
        {items.map((item, i) => {
          const prev = items[i + 1];
          const summary = item.ai_summary || item.summary || 'Changed';
          return (
            <li key={item.id} className={clsx(s.row, i === 0 && s.newest)}>
              <span className={s.marker} aria-hidden="true">
                <svg viewBox="-10 -10 20 20" width="18" height="18">
                  <circle r="7.5" fill="var(--blued-deep)" stroke="var(--blued)" strokeWidth="1.2" />
                  <line x1="-4.5" y1="-1.2" x2="4.5" y2="1.2" stroke="#0c1a55" strokeWidth="1.6" strokeLinecap="round" />
                  {i === 0 && <circle r="2.6" cx="0" cy="0" fill="var(--lume)" />}
                </svg>
              </span>
              <div className={s.when}>
                <Tooltip tip={exact(item.created_at, timeZone)}><span className="num">{dayAndTime(item.created_at, timeZone)}</span></Tooltip>
              </div>
              <div className={s.body}>
                <p className={s.summary}>
                  {item.ai_summary && <Sparkle size={15} weight="light" className={s.sparkle} aria-label="AI summary" />}
                  {item.is_baseline ? 'New starting point (regions changed)' : item.is_first ? 'First version saved' : summary}
                </p>
                <div className={s.meta}>
                  {!item.is_first && !item.is_baseline && (
                    <span className="num">
                      <span className={s.added}>+{item.added_lines}</span>{' '}
                      <span className={s.removed}>&minus;{item.removed_lines}</span>
                    </span>
                  )}
                  {item.keyword_hit && <span className={s.keyword}>Triggered by "{item.keyword_hit}"</span>}
                  {prev && !item.is_baseline && (
                    <Link to={`/pages/${watchId}/compare?a=${prev.id}&b=${item.id}`}>Compare with previous</Link>
                  )}
                  <label className={s.pick}>
                    <input type="checkbox" checked={picked.includes(item.id)} onChange={() => toggle(item.id)} />
                    <span>Select</span>
                  </label>
                </div>
              </div>
              {item.thumbnail_url && (
                <img className={s.thumb} src={mediaUrl(item.thumbnail_url)} alt="" loading="lazy" width={160} height={100} />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
