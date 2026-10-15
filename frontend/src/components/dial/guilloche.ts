/**
 * guilloche.ts — turns a page's 8-hex-digit dial seed into the engraved pattern on its dial.
 *
 * Guilloché is the engine-turned engraving on fine watch dials: many closed curves, each a circle whose
 * radius wobbles in a regular rhythm, nested inside each other so they form petals, waves or lattices.
 *
 * The maths, in simple words:
 *   - A plain circle in polar coordinates is r(θ) = base (the same radius at every angle θ).
 *   - Add A·sin(kθ + φ) and the radius wobbles k times around the circle: a flower with k petals.
 *   - Add a smaller A2·sin(k·m·θ − φ/2) and each petal gets a finer ripple (the "engraving" detail).
 *   - Draw N of these curves with slowly growing `base` and shifting phase φ, and the curves cross
 *     each other in the interference pattern that makes guilloché shimmer.
 * The seed feeds a tiny deterministic random generator (mulberry32), so a given URL always produces
 * exactly the same dial, on every device, forever — like a serial number.
 *
 * Exports are pure functions (no React), memoised because a dashboard may draw 30 dials.
 */

export type GuillocheStyle = 'rosette' | 'wave' | 'woven' | 'lattice';
export type GuillocheDetail = 'sm' | 'md' | 'lg';

export interface GuillochePath {
  /** SVG path data, centred on (0, 0). */
  d: string;
  /** Per-line opacity: stronger in the middle rings, fainter at the centre and edge. */
  opacity: number;
  /** Position of the line from inner (0) to outer (1); used to stagger the engrave animation. */
  t: number;
}

export interface GuillocheParams {
  style: GuillocheStyle;
  k: number;
  N: number;
  A: number;
  m: number;
  A2: number;
  turns: number;
}

/**
 * mulberry32: a tiny, fast pseudo-random number generator. Same seed in, same sequence out.
 * Returns a function that yields numbers in [0, 1).
 */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Draw the pattern parameters from the seed, always in the same order (so a seed is stable). */
export function guillocheParams(seedHex: string, radius: number, detail: GuillocheDetail): GuillocheParams {
  const seed = parseInt(seedHex.slice(0, 8) || '0', 16) || 1;
  const rnd = mulberry32(seed);
  const styles: GuillocheStyle[] = ['rosette', 'wave', 'woven', 'lattice'];
  const style = styles[Math.floor(rnd() * 4)];
  const k = 9 + Math.floor(rnd() * 16); // integer in [9, 24]
  const nDraw = rnd();
  let N = style === 'lattice' ? 24 + Math.floor(nDraw * 9) : 36 + Math.floor(nDraw * 25); // [24,32] or [36,60]
  if (detail === 'sm') N = Math.round(N * 0.6);
  const A = (0.035 + rnd() * 0.045) * radius;
  const m = rnd() < 0.5 ? 2 : 3;
  const A2 = A * (0.15 + rnd() * 0.3);
  const turns = 0.5 + rnd() * 1.5;
  return { style, k, N, A, m, A2, turns };
}

const STEPS: Record<GuillocheDetail, number> = { lg: 900, md: 480, sm: 300 };
const memo = new Map<string, GuillochePath[]>();

/** Build one closed curve r(θ) = base + A·sin(kθ + φ) + A2·sin(k·m·θ − φ/2) as an SVG path. */
function curve(base: number, phi: number, amp: number, p: GuillocheParams, steps: number): string {
  const parts: string[] = [];
  for (let s = 0; s < steps; s++) {
    const theta = (s / steps) * Math.PI * 2;
    const r = base + amp * Math.sin(p.k * theta + phi) + p.A2 * Math.sin(p.k * p.m * theta - phi / 2);
    const x = (r * Math.cos(theta)).toFixed(2);
    const y = (r * Math.sin(theta)).toFixed(2);
    parts.push(`${s === 0 ? 'M' : 'L'}${x} ${y}`);
  }
  parts.push('Z');
  return parts.join('');
}

/**
 * The main export: every engraved line for a dial of the given radius and detail level.
 * Results are cached in memory (and in sessionStorage when small enough) by seed + radius + detail.
 */
export function guillochePaths(seedHex: string, opts: { radius: number; detail: GuillocheDetail }): GuillochePath[] {
  const { radius: R, detail } = opts;
  const key = `${seedHex}:${R}:${detail}`;
  const cached = memo.get(key);
  if (cached) return cached;
  const stored = readSession(key);
  if (stored) {
    memo.set(key, stored);
    return stored;
  }

  const p = guillocheParams(seedHex, R, detail);
  const steps = STEPS[detail];
  const out: GuillochePath[] = [];
  const opacityAt = (t: number) => 0.35 + 0.45 * (0.5 + 0.5 * Math.sin(Math.PI * t));

  for (let i = 0; i < p.N; i++) {
    const t = i / p.N;
    if (p.style === 'rosette') {
      out.push({ d: curve(R * (0.12 + 0.62 * t), 2 * Math.PI * t * p.turns, p.A, p, steps), opacity: opacityAt(t), t });
    } else if (p.style === 'wave') {
      out.push({ d: curve(R * (0.1 + 0.64 * t), 1.2 * Math.sin(2 * Math.PI * t * p.turns), p.A, p, steps), opacity: opacityAt(t), t });
    } else if (p.style === 'woven') {
      out.push({ d: curve(R * (0.4 + 0.18 * t), 2 * Math.PI * t * p.turns, p.A * 2.6, p, steps), opacity: opacityAt(t), t });
    } else {
      // lattice: two families turning in opposite directions cross each other like a woven net.
      for (const s of [1, -1]) {
        out.push({ d: curve(R * (0.12 + 0.62 * t), s * 2 * Math.PI * t * p.turns, p.A, p, steps), opacity: opacityAt(t), t });
      }
    }
  }
  memo.set(key, out);
  writeSession(key, out);
  return out;
}

function readSession(key: string): GuillochePath[] | null {
  try {
    const raw = sessionStorage.getItem('gq:' + key);
    return raw ? (JSON.parse(raw) as GuillochePath[]) : null;
  } catch {
    return null;
  }
}

function writeSession(key: string, value: GuillochePath[]): void {
  try {
    const raw = JSON.stringify(value);
    // Large dials produce hundreds of KB; storing those would quickly fill the 5 MB quota.
    if (raw.length < 160_000) sessionStorage.setItem('gq:' + key, raw);
  } catch {
    /* storage full or unavailable: the in-memory cache still works */
  }
}
