/**
 * Jewel.tsx — the status jewel at 12 o'clock on every dial: a cabochon (a polished dome-shaped gem)
 * drawn as a circle with a radial gradient and a small white specular dot. Its colour is the status:
 * lume = OK, ruby = error, topaz = blocked, moonstone = pending, rhodium = paused.
 * A glint sweeps across it once when the dial is hovered (CSS in Dial.module.css).
 */
import s from './Dial.module.css';

export type JewelStatus = 'ok' | 'error' | 'blocked' | 'pending' | 'paused';

const COLOURS: Record<JewelStatus, string> = {
  ok: 'var(--lume)',
  error: 'var(--ruby)',
  blocked: 'var(--topaz)',
  pending: 'var(--moonstone)',
  paused: 'var(--rhodium)',
};

/** Rendered inside the dial's SVG; (cx, cy, r) are in the dial's coordinate units. */
export function Jewel({ status, cx, cy, r, gradientId }: { status: JewelStatus; cx: number; cy: number; r: number; gradientId: string }) {
  const colour = COLOURS[status];
  return (
    <g className={s.jewel}>
      <defs>
        <radialGradient id={gradientId} cx="38%" cy="32%" r="75%">
          <stop offset="0%" style={{ stopColor: '#ffffff', stopOpacity: 0.85 }} />
          <stop offset="22%" style={{ stopColor: colour }} />
          <stop offset="100%" style={{ stopColor: colour, stopOpacity: 0.55 }} />
        </radialGradient>
      </defs>
      {/* bezel (the setting that holds the stone) */}
      <circle cx={cx} cy={cy} r={r * 1.35} fill="none" stroke="var(--dial-ring)" strokeWidth={0.6} opacity={0.7} />
      {status === 'ok' && <circle cx={cx} cy={cy} r={r * 1.6} fill="var(--lume-glow)" opacity={0.35} className={s.jewelGlow} />}
      <circle cx={cx} cy={cy} r={r} fill={`url(#${gradientId})`} />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(0,0,0,0.35)" strokeWidth={0.5} />
      <circle cx={cx - r * 0.35} cy={cy - r * 0.38} r={r * 0.22} fill="#fff" opacity={0.9} />
      <ellipse className={s.glint} cx={cx} cy={cy} rx={r * 0.25} ry={r * 1.1} fill="#fff" opacity={0} />
    </g>
  );
}
