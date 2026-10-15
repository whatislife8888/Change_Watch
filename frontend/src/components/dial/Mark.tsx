/**
 * Mark.tsx — the ChangeWatch logo: a tiny guilloché dial with a blued hand.
 * Used in the top bar and on the auth pages. The engraving comes from the same generator as the
 * real dials, with a fixed seed, so the logo is literally "a ChangeWatch dial".
 */
import { useMemo } from 'react';
import { guillochePaths } from './guilloche';

const LOGO_SEED = 'c0ffee15';

export function Mark({ size = 28, title = 'ChangeWatch' }: { size?: number; title?: string }) {
  const R = 100;
  const paths = useMemo(() => guillochePaths(LOGO_SEED, { radius: R * 0.78, detail: 'sm' }).filter((_, i) => i % 2 === 0), []);
  return (
    <svg width={size} height={size} viewBox="-110 -110 220 220" role="img" aria-label={title}>
      <circle r="106" fill="none" stroke="var(--rhodium)" strokeWidth="8" opacity="0.8" />
      <circle r="98" fill="var(--surface-sunken)" />
      <g fill="none" stroke="var(--engrave)" strokeWidth="3.2" vectorEffect="non-scaling-stroke">
        {paths.map((p, i) => (
          <path key={i} d={p.d} opacity={p.opacity} strokeWidth={1} vectorEffect="non-scaling-stroke" />
        ))}
      </g>
      <line x1="0" y1="14" x2="0" y2="-82" stroke="var(--blued)" strokeWidth="9" strokeLinecap="round" transform="rotate(38)" />
      <circle r="12" fill="var(--blued-deep)" stroke="var(--blued)" strokeWidth="3" />
    </svg>
  );
}
