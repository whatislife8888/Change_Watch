/**
 * Sparkline.tsx — a tiny trend line for list rows (no axes, no library).
 * Decorative: the latest value is always shown as text beside it, so nothing depends on reading the line.
 * Kept separate from NumberChart so the dashboard doesn't load the charting library.
 */
import s from './NumberChart.module.css';

/** Tiny trend line (no axes) for lists. Decorative: the latest value is always shown as text beside it. */
export function Sparkline({ values, width = 96, height = 24 }: { values: number[]; width?: number; height?: number }) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1);
  const d = values.map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)} ${(height - 2 - ((v - min) / span) * (height - 4)).toFixed(1)}`).join('');
  const last = values[values.length - 1];
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" className={s.spark}>
      <path d={d} fill="none" stroke="var(--text-3)" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={width} cy={height - 2 - ((last - min) / span) * (height - 4)} r={2.5} fill="var(--lume)" />
    </svg>
  );
}
