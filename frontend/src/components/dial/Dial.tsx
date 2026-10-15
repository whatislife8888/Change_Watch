/**
 * Dial.tsx — the signature component: every watched page drawn as its own watch dial.
 *
 * Layers, from back to front:
 *   1. Case ring: a thin metallic ring (CSS conic-gradient) that holds the dial.
 *   2. Face: radial "fumé" gradient + sunburst brushing + a pointer-following specular highlight.
 *   3. Guilloché: the engraved pattern generated from the page's URL seed (guilloche.ts).
 *   4. Hairline ring at 0.80R and the railway-track chapter ring (60 ticks between 0.84R and 0.93R).
 *   5. Status jewel at 12 o'clock, date window at 3 o'clock, optional sub-counter at 6 o'clock.
 *   6. The blued sweep hand (progress to the next check) — or, in clock mode, real hour/minute hands.
 *   7. While a check runs: the hand holds still and a thin lume arc travels around the chapter ring.
 *
 * Coordinates: the SVG uses a viewBox from -100 to 100, so R (the face radius) is always 100 units,
 * whatever the pixel size. Strokes use vector-effect="non-scaling-stroke" so line widths stay crisp
 * hairlines in screen pixels at every size.
 */
import clsx from 'clsx';
import { motion } from 'motion/react';
import { memo, useEffect, useId, useMemo, useRef, useState, type CSSProperties } from 'react';
import { usePrefersReducedMotion } from '../../design/motion';
import { relative, short, toMs } from '../../lib/time';
import { DateWindow } from './DateWindow';
import s from './Dial.module.css';
import { guillochePaths, type GuillocheDetail } from './guilloche';
import { Jewel, type JewelStatus } from './Jewel';
import { HandShape, ScrewCap, SweepHand } from './SweepHand';
import { useSpecular } from './useSpecular';
import { Odometer } from '../odometer/Odometer';

const R = 100;

export interface DialProps {
  seed: string;
  /** Outer diameter in px. */
  size: number;
  status?: JewelStatus;
  name?: string;
  lastCheckedAt?: string | null;
  lastChangedAt?: string | null;
  nextDueAt?: string | null;
  intervalMinutes?: number;
  running?: boolean;
  paused?: boolean;
  /** Sub-counter value at 6 o'clock (large dials with number tracking). */
  subValue?: string | null;
  /** Changing this replays the engraving once and pulses a salmon halo (a change was detected). */
  engraveKey?: string | number;
  /** Engrave the pattern in when the dial first appears. */
  engrave?: boolean;
  /** Stagger index for the wind-up animation on page load. */
  windIndex?: number;
  /** Tilt + specular highlight follow the pointer. */
  interactive?: boolean;
  /** Clock mode: show the current time with hour, minute and seconds hands (landing hero). */
  clock?: boolean;
  showDate?: boolean;
  /** Purely decorative (no accessible label). */
  decorative?: boolean;
  layoutId?: string;
  className?: string;
  /** Cross-fade between patterns when the seed changes (live preview while typing). */
  crossfade?: boolean;
}

function detailFor(size: number): GuillocheDetail {
  if (size <= 200) return 'sm';
  if (size <= 320) return 'md';
  return 'lg';
}

/** The engraved guilloché field, memoised so it only recomputes when seed or detail changes. */
const Guilloche = memo(function Guilloche({ seed, detail, animate, clipId, strokeWidth }: {
  seed: string; detail: GuillocheDetail; animate: 'none' | 'reveal' | 'engrave'; clipId: string; strokeWidth: number;
}) {
  const paths = useMemo(() => guillochePaths(seed, { radius: R, detail }), [seed, detail]);
  return (
    <g clipPath={`url(#${clipId})`} className={animate === 'reveal' ? s.reveal : undefined}>
      <g fill="none" stroke="var(--engrave)" strokeWidth={strokeWidth} className={s.engraving}>
        {paths.map((p, i) => (
          <path
            key={i}
            d={p.d}
            opacity={p.opacity}
            // pathLength="1" tells the browser to treat the whole curve as length 1, so a dash of
            // length 1 offset by 1 hides it, and animating the offset to 0 "draws" it — the engrave effect.
            pathLength={animate === 'engrave' ? 1 : undefined}
            className={animate === 'engrave' ? s.engravePath : undefined}
            style={animate === 'engrave' ? ({ ['--i' as string]: i } as CSSProperties) : undefined}
          />
        ))}
      </g>
    </g>
  );
});

function ChapterRing({ size }: { size: number }) {
  const ticks = useMemo(() => {
    const out: { x1: number; y1: number; x2: number; y2: number; major: boolean }[] = [];
    for (let i = 0; i < 60; i++) {
      const a = (i / 60) * Math.PI * 2;
      const major = i % 5 === 0;
      const r1 = major ? 0.84 * R : 0.88 * R;
      const r2 = 0.93 * R;
      out.push({ x1: r1 * Math.sin(a), y1: -r1 * Math.cos(a), x2: r2 * Math.sin(a), y2: -r2 * Math.cos(a), major });
    }
    return out;
  }, []);
  const thin = size < 200 ? 0.6 : 0.8;
  return (
    <g stroke="var(--dial-tick)" fill="none">
      <circle r={0.8 * R} strokeWidth={0.5} opacity={0.55} vectorEffect="non-scaling-stroke" />
      <circle r={0.88 * R} strokeWidth={thin * 0.8} opacity={0.6} vectorEffect="non-scaling-stroke" />
      <circle r={0.93 * R} strokeWidth={thin * 0.8} opacity={0.6} vectorEffect="non-scaling-stroke" />
      {ticks.map(({ major, ...line }, i) => (
        <line key={i} {...line} strokeWidth={major ? thin * 2 : thin} opacity={major ? 0.95 : 0.6} vectorEffect="non-scaling-stroke" />
      ))}
    </g>
  );
}

/** Real-time hour + minute hands for the landing hero (plus a 60-second sweep). */
function ClockHands({ reduced }: { reduced: boolean }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), reduced ? 30_000 : 10_000);
    return () => window.clearInterval(id);
  }, [reduced]);
  const minutes = now.getMinutes() + now.getSeconds() / 60;
  const hours = (now.getHours() % 12) + minutes / 60;
  const seconds = now.getSeconds() + now.getMilliseconds() / 1000;
  return (
    <>
      <svg viewBox="-100 -100 200 200" className={s.handSvg} aria-hidden="true">
        <g className={reduced ? undefined : s.clockSet} style={{ ['--to' as string]: `${hours * 30}deg` } as CSSProperties}>
          <g style={{ transform: `rotate(${hours * 30}deg)` }}><HandShape length={50} tail={12} width={5.5} /></g>
        </g>
        <g className={reduced ? undefined : s.clockSet} style={{ ['--to' as string]: `${minutes * 6}deg` } as CSSProperties}>
          <g style={{ transform: `rotate(${minutes * 6}deg)` }}><HandShape length={76} tail={14} width={3.8} /></g>
        </g>
      </svg>
      <SweepHand periodSec={60} elapsedSec={seconds} frozen={false} reduced={reduced} syncKey="clock" windIndex={reduced ? undefined : 0} />
    </>
  );
}

function DialImpl(props: DialProps) {
  const {
    seed, size, status = 'pending', name, lastCheckedAt, lastChangedAt, nextDueAt, intervalMinutes = 60,
    running = false, paused = false, subValue, engraveKey, engrave = false, windIndex, interactive = false,
    clock = false, showDate = true, decorative = false, layoutId, className, crossfade = false,
  } = props;
  const reduced = usePrefersReducedMotion();
  const uid = useId().replace(/:/g, '');
  const detail = detailFor(size);
  const { ref, handlers } = useSpecular<HTMLDivElement>(interactive);

  // Decide how the engraving should appear: on first mount (if asked) and again whenever engraveKey changes.
  const firstKey = useRef(engraveKey);
  const [halo, setHalo] = useState(false);
  const changed = engraveKey !== firstKey.current;
  useEffect(() => {
    if (!changed) return;
    setHalo(true);
    const t = window.setTimeout(() => setHalo(false), 1300);
    return () => window.clearTimeout(t);
  }, [engraveKey, changed]);
  let animate: 'none' | 'reveal' | 'engrave' = 'none';
  if (!reduced && (engrave || changed)) animate = detail === 'sm' ? 'reveal' : 'engrave';

  // Sweep-hand timing from the real schedule.
  const lastMs = toMs(lastCheckedAt);
  const nextMs = toMs(nextDueAt);
  const periodSec = lastMs && nextMs && nextMs > lastMs ? (nextMs - lastMs) / 1000 : intervalMinutes * 60;
  const elapsedSec = lastMs ? (Date.now() - lastMs) / 1000 : 0;
  const syncKey = `${lastCheckedAt ?? ''}|${nextDueAt ?? ''}|${running}`;

  const jewelStatus: JewelStatus = paused ? 'paused' : status;
  // Engraving line width: 0.6 px (small) to 0.9 px (large), converted to SVG units (200 units = `size` px).
  // Why not vector-effect="non-scaling-stroke": Chromium then measures dashes in screen pixels while
  // pathLength is in SVG units, so the engrave animation would stop half-drawn.
  const strokePx = detail === 'sm' ? 0.6 : detail === 'md' ? 0.75 : 0.9;
  const strokeWidth = (strokePx * 200) / size;
  const casePad = Math.max(3, Math.round(size * 0.028));

  const label = decorative
    ? undefined
    : clock
      ? 'ChangeWatch dial showing the current time'
      : `${name ?? 'Page'}: ${paused ? 'paused' : status === 'ok' ? 'OK' : status}. ` +
        `Checked ${relative(lastCheckedAt)}, changed ${lastChangedAt ? relative(lastChangedAt) : 'never'}` +
        (paused ? '.' : running ? ', checking now.' : `, next check ${relative(nextDueAt)}.`);

  return (
    <motion.div
      layoutId={layoutId}
      className={clsx(s.dial, paused && s.paused, halo && s.halo, interactive && s.interactive, className)}
      style={{ width: size, maxWidth: '100%', aspectRatio: '1 / 1', padding: casePad }}
      role={decorative ? undefined : 'img'}
      aria-label={label}
      aria-hidden={decorative || undefined}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
    >
      <div ref={ref} className={s.tilt} {...handlers}>
        <div className={s.face}>
          <svg viewBox="-100 -100 200 200" className={s.svg} aria-hidden="true">
            <defs>
              <clipPath id={`clip-${uid}`}>
                <circle r={0.79 * R} />
              </clipPath>
            </defs>
            {crossfade ? (
              <g key={seed} className={s.crossfade}>
                <Guilloche seed={seed} detail={detail} animate="none" clipId={`clip-${uid}`} strokeWidth={strokeWidth} />
              </g>
            ) : (
              <Guilloche key={String(engraveKey ?? 'k')} seed={seed} detail={detail} animate={animate} clipId={`clip-${uid}`} strokeWidth={strokeWidth} />
            )}
            <ChapterRing size={size} />
            {running && !paused && (
              <g className={s.runArc}>
                <circle r={0.905 * R} fill="none" stroke="var(--lume)" strokeWidth={((size < 200 ? 1.6 : 2.2) * 200) / size}
                  pathLength={1} strokeDasharray="0.14 0.86" strokeLinecap="round" />
              </g>
            )}
            {!clock && <Jewel status={jewelStatus} cx={0} cy={-0.62 * R} r={0.065 * R} gradientId={`jewel-${uid}`} />}
            {subValue != null && (
              <g>
                <circle cx={0} cy={0.44 * R} r={0.2 * R} fill="var(--dial-face-3)" opacity={0.55} />
                <circle cx={0} cy={0.44 * R} r={0.2 * R} fill="none" stroke="var(--dial-ring)" strokeWidth={0.6} vectorEffect="non-scaling-stroke" />
              </g>
            )}
          </svg>
          {showDate && !clock && <DateWindow text={short(lastChangedAt)} fontSize={Math.max(9, size * 0.042)} />}
          {subValue != null && (
            <div className={s.subCounter} style={{ fontSize: Math.max(10, size * 0.04) }} aria-hidden="true">
              <Odometer value={subValue} />
            </div>
          )}
          <div className={s.specular} aria-hidden="true" />
          {clock ? (
            <ClockHands reduced={reduced} />
          ) : (
            <SweepHand
              periodSec={periodSec}
              elapsedSec={elapsedSec}
              frozen={paused || running}
              windIndex={windIndex}
              reduced={reduced}
              syncKey={syncKey}
            />
          )}
          {clock && (
            <svg viewBox="-100 -100 200 200" className={s.handSvg} aria-hidden="true"><ScrewCap r={5.5} /></svg>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export const Dial = memo(DialImpl);
