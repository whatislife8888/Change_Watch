/**
 * SweepHand.tsx — the single blued-steel hand that shows progress toward the next check.
 *
 * 12 o'clock = just checked; one full turn = the next check is due.
 *
 * Why CSS and not JavaScript per frame: a dashboard can show 30 dials. Instead of recalculating 30
 * angles 60 times a second, each hand gets one CSS animation (`sweep`) lasting the check interval,
 * started "in the past" with a negative delay (= seconds since the last check). The browser's
 * compositor then turns the hand smoothly with almost no CPU.
 *   --period  = seconds between checks       --elapsed = seconds since the last check
 * When new data arrives (last_checked_at changes) the component re-mounts the rotor, re-syncing it.
 *
 * The outer "wind" wrapper plays once on page load: it starts rotated back to 12 o'clock and springs
 * forward to the true position, so every dial appears to wind itself (40 ms stagger per dial).
 * With reduced motion there is no animation; the angle is recomputed every 30 seconds instead.
 */
import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import s from './Dial.module.css';

interface SweepHandProps {
  periodSec: number;
  /** Seconds since the last check, measured when the data arrived. */
  elapsedSec: number;
  /** Paused watch: the hand stops. Running check: the hand holds still while the lume arc travels. */
  frozen: boolean;
  /** Play the wind-up animation with this stagger index (undefined = no wind). */
  windIndex?: number;
  reduced: boolean;
  syncKey: string;
}

export function SweepHand({ periodSec, elapsedSec, frozen, windIndex, reduced, syncKey }: SweepHandProps) {
  const period = Math.max(1, periodSec);
  const elapsed = Math.min(Math.max(0, elapsedSec), period);
  const overdue = elapsedSec >= period;

  // Reduced motion: recompute the angle every 30 s instead of animating.
  const [tickNow, setTickNow] = useState(() => Date.now());
  const startedAt = useMemo(() => Date.now(), [syncKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!reduced) return;
    const id = window.setInterval(() => setTickNow(Date.now()), 30_000);
    return () => window.clearInterval(id);
  }, [reduced]);

  let rotorStyle: CSSProperties;
  if (reduced) {
    const live = Math.min(period, elapsed + (frozen ? 0 : (tickNow - startedAt) / 1000));
    rotorStyle = { transform: `rotate(${(live / period) * 360}deg)` };
  } else if (overdue) {
    rotorStyle = { transform: 'rotate(360deg)' };
  } else {
    rotorStyle = {
      ['--period' as string]: `${period}s`,
      ['--elapsed' as string]: `${elapsed}s`,
      animationPlayState: frozen ? 'paused' : 'running',
    };
  }

  const windFrom = -((overdue ? 1 : elapsed / period) * 360);
  const wind = windIndex !== undefined && !reduced;

  return (
    <div
      className={wind ? s.handWind : s.handLayer}
      style={wind ? { ['--wind-from' as string]: `${windFrom}deg`, ['--wind-delay' as string]: `${windIndex * 40}ms` } : undefined}
      aria-hidden="true"
    >
      <div key={syncKey} className={reduced || overdue ? s.handStatic : s.handRotor} style={rotorStyle}>
        <svg viewBox="-100 -100 200 200" className={s.handSvg}>
          <HandShape length={86} tail={18} width={2.6} />
        </svg>
      </div>
      <svg viewBox="-100 -100 200 200" className={s.handSvg}>
        <ScrewCap r={5.2} />
      </svg>
    </div>
  );
}

/** The blued-steel hand drawn pointing at 12 o'clock: a slim tapered needle with a round counterweight. */
export function HandShape({ length, tail, width }: { length: number; tail: number; width: number }) {
  return (
    <g>
      <defs>
        <linearGradient id="blued-steel" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="#2440C2" />
          <stop offset="55%" stopColor="#5B78F6" />
          <stop offset="100%" stopColor="#8FA4FF" />
        </linearGradient>
      </defs>
      <path
        d={`M ${-width / 2} ${tail} L ${-width * 0.22} ${-length} L ${width * 0.22} ${-length} L ${width / 2} ${tail} Z`}
        fill="url(#blued-steel)"
        className={s.handShadow}
      />
      <circle cx="0" cy={tail - 1} r={Math.min(3.2, width * 0.85)} fill="#2440C2" />
    </g>
  );
}

/** Blued screw head at the centre, with its slot. */
export function ScrewCap({ r }: { r: number }) {
  return (
    <g>
      <circle r={r} fill="#2440C2" stroke="#7D93F8" strokeWidth={0.8} />
      <line x1={-r * 0.65} y1={-r * 0.2} x2={r * 0.65} y2={r * 0.2} stroke="#101F66" strokeWidth={1.1} strokeLinecap="round" />
      <circle cx={-r * 0.35} cy={-r * 0.45} r={r * 0.22} fill="#fff" opacity={0.55} />
    </g>
  );
}
