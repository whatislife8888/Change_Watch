/**
 * Movement.tsx — a live view of the scheduler, drawn as a watch movement.
 *
 * Three gears, an escape wheel and a balance wheel on a Côtes de Genève plate. It is driven by the SSE
 * `queue` event (every 3 s):
 *   idle          → gears stand still; the balance wheel swings slowly (3 s)
 *   checks running → the gears turn (faster with more running checks) and the balance beats at 1 s
 *   one ruby jewel per worker glows lume while that worker is busy
 * The label says it in plain words: "2 checks running, 5 waiting". It makes the queue, the workers and
 * the politeness limits visible, which is useful in a demo.
 *
 * The rotation speeds respect the gear ratios (ω2 = −ω1·n1/n2), so the teeth genuinely mesh.
 */
import clsx from 'clsx';
import { useMemo, type CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { useQueueStats } from '../../realtime/useEvents';
import { gearPath, meshCentre, meshPhaseDeg, pitchRadius, type GearSpec } from './gears';
import s from './Movement.module.css';

const A: GearSpec = { n: 40, m: 2 };
const B: GearSpec = { n: 14, m: 2 }; // pinion on B's axle
const B2: GearSpec = { n: 30, m: 1.4 }; // wheel on the same axle as B
const C: GearSpec = { n: 10, m: 1.4 }; // escape pinion
const ESC: GearSpec = { n: 15, m: 1.9 }; // escape wheel, same axle as C

const centreA = { x: 66, y: 90 };
const alphaAB = (-25 * Math.PI) / 180;
const centreB = meshCentre(centreA, A, B, alphaAB);
const alphaBC = (12 * Math.PI) / 180;
const centreC = meshCentre(centreB, B2, C, alphaBC);
const centreBal = { x: 204, y: 82 };

function Gear({ spec, cx, cy, phase, period, reverse, running, jewel, spokes = 5 }: {
  spec: GearSpec; cx: number; cy: number; phase: number; period: number; reverse: boolean; running: boolean;
  jewel?: 'idle' | 'busy'; spokes?: number;
}) {
  const d = useMemo(() => gearPath(spec), [spec]);
  const rp = pitchRadius(spec);
  const rf = rp - 1.25 * spec.m;
  const hollow = rf * 0.74;
  const style = {
    animationDuration: `${period}s`,
    animationDirection: reverse ? 'reverse' : 'normal',
    animationPlayState: running ? 'running' : 'paused',
  } as CSSProperties;
  return (
    <g transform={`translate(${cx} ${cy}) rotate(${phase})`}>
      <g className={s.spin} style={style}>
        <path d={d} className={s.gear} />
        {rf > 9 && (
          <>
            <circle r={hollow} className={s.hole} />
            {Array.from({ length: spokes }, (_, i) => (
              <rect key={i} x={-1.3} y={-hollow} width={2.6} height={hollow} className={s.gear} transform={`rotate(${(i * 360) / spokes})`} />
            ))}
            <circle r={rf * 0.22} className={s.gear} />
          </>
        )}
      </g>
      <circle r={Math.max(2.4, rp * 0.09)} className={clsx(s.jewel, jewel === 'busy' && s.jewelBusy)} />
    </g>
  );
}

export function Movement({ size = 'sm', linkToSystem = false }: { size?: 'sm' | 'lg'; linkToSystem?: boolean }) {
  const stats = useQueueStats();
  const running = stats.running > 0;
  // Gear A takes 24 s per turn with one check running, faster with more (never below 6 s).
  const periodA = Math.max(6, 24 / Math.max(1, stats.running));
  const periodB = (periodA * B.n) / A.n; // ω_B = ω_A·n_A/n_B
  const periodC = (periodB * C.n) / B2.n;
  const busy = stats.workers_busy;

  const label = running || stats.waiting
    ? `${stats.running} check${stats.running === 1 ? '' : 's'} running, ${stats.waiting} waiting`
    : 'All quiet. Waiting for the next check.';

  const body = (
    <div className={clsx(s.movement, size === 'lg' && s.large)}>
      <div className={clsx(s.plate, 'tex-cotes')} aria-hidden="true">
        <svg viewBox="0 0 240 160" className={s.svg}>
          {/* bridges (the shaped plates that hold the axles) */}
          <path d="M20 140 C 60 120, 110 120, 150 100 L 175 60 L 168 50 L 140 88 C 100 108, 60 110, 18 128 Z" className={s.bridge} />
          <Gear spec={A} cx={centreA.x} cy={centreA.y} phase={(alphaAB * 180) / Math.PI} period={periodA} reverse={false} running={running}
            jewel={busy[0] ? 'busy' : 'idle'} spokes={5} />
          <Gear spec={B2} cx={centreB.x} cy={centreB.y} phase={(alphaBC * 180) / Math.PI} period={periodB} reverse running={running} spokes={4} />
          <Gear spec={B} cx={centreB.x} cy={centreB.y} phase={meshPhaseDeg(alphaAB, B)} period={periodB} reverse running={running}
            jewel={busy[1] ? 'busy' : 'idle'} />
          <Gear spec={ESC} cx={centreC.x} cy={centreC.y} phase={meshPhaseDeg(alphaBC, C)} period={periodC} reverse={false} running={running} spokes={3} />
          <Gear spec={C} cx={centreC.x} cy={centreC.y} phase={meshPhaseDeg(alphaBC, C)} period={periodC} reverse={false} running={running}
            jewel={busy[2] ? 'busy' : 'idle'} />
          {/* balance wheel: swings back and forth; faster while checks run */}
          <g transform={`translate(${centreBal.x} ${centreBal.y})`}>
            <g className={s.balance} style={{ animationDuration: running ? '1s' : '3s' }}>
              <circle r="25" className={s.balanceRim} />
              <circle r="21.5" className={s.hole} />
              {[0, 120, 240].map((a) => <rect key={a} x="-1.2" y="-22" width="2.4" height="22" className={s.gear} transform={`rotate(${a})`} />)}
              <path d="M0 0 m-12 0 a12 12 0 1 0 24 0 a10 10 0 1 0 -20 0 a8 8 0 1 0 16 0" className={s.hairspring} />
            </g>
            <circle r="3" className={clsx(s.jewel, running && s.jewelBusy)} />
          </g>
          {/* screws */}
          {[[24, 30], [222, 140], [150, 140]].map(([x, y]) => (
            <g key={`${x}-${y}`} transform={`translate(${x} ${y})`}>
              <circle r="4.2" className={s.screw} />
              <line x1="-3" y1="-1" x2="3" y2="1" className={s.screwSlot} />
            </g>
          ))}
        </svg>
      </div>
      <p className={s.label} aria-live="polite">{label}</p>
    </div>
  );

  return linkToSystem ? (
    <Link to="/system" className={s.link} aria-label={`${label} Open the system view.`}>{body}</Link>
  ) : body;
}
