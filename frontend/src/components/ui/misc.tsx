/**
 * misc.tsx — small presentational pieces: Skeleton (brushed-metal loading shimmer), EmptyState,
 * StatusText (jewel + word — status is never colour alone), Tooltip, and Chip (filter toggles).
 */
import clsx from 'clsx';
import { useId, useState, type ButtonHTMLAttributes, type CSSProperties, type ReactNode } from 'react';
import s from './ui.module.css';

/** Placeholder block shown while data loads. */
export function Skeleton({ width = '100%', height = 16, radius, style }: { width?: number | string; height?: number | string; radius?: number | string; style?: CSSProperties }) {
  return <div className={clsx(s.skeleton, 'tex-shimmer')} style={{ width, height, borderRadius: radius, ...style }} aria-hidden="true" />;
}

/** Friendly "nothing here yet" message that invites the next action. */
export function EmptyState({ title, body, children, visual }: { title: string; body?: ReactNode; children?: ReactNode; visual?: ReactNode }) {
  return (
    <div className={s.empty}>
      {visual}
      <h2 className={s.emptyTitle}>{title}</h2>
      {body && <p className={s.emptyBody}>{body}</p>}
      {children}
    </div>
  );
}

export type StatusKind = 'ok' | 'error' | 'blocked' | 'pending' | 'paused' | 'running';

export const STATUS_WORDS: Record<StatusKind, string> = {
  ok: 'OK',
  error: 'Error',
  blocked: 'Blocked',
  pending: 'Pending',
  paused: 'Paused',
  running: 'Checking',
};

/** A tiny jewel followed by the status word, e.g. ● OK. */
export function StatusText({ status, children }: { status: StatusKind; children?: ReactNode }) {
  const cls = status === 'error' ? s.error_ : s[status];
  return (
    <span className={clsx(s.status, cls)}>
      <span className={s.statusJewel} aria-hidden="true" />
      {children ?? STATUS_WORDS[status]}
    </span>
  );
}

/** Shows `tip` above its child on hover and keyboard focus; on touch screens (no hover) a tap toggles it. */
export function Tooltip({ tip, children }: { tip: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  if (!tip) return <>{children}</>;
  return (
    <span
      className={s.tipWrap}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onPointerUp={(e) => { if (e.pointerType === 'touch') setOpen((o) => !o); }}
      aria-describedby={open ? id : undefined}
    >
      {children}
      {open && <span role="tooltip" id={id} className={s.tip}>{tip}</span>}
    </span>
  );
}

/** A filter chip that can be on or off (aria-pressed). */
export function Chip({ active, count, children, ...rest }: { active: boolean; count?: number } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button type="button" className={s.chip} aria-pressed={active} {...rest}>
      {children}
      {count !== undefined && <span className={s.chipCount}>{count}</span>}
    </button>
  );
}
