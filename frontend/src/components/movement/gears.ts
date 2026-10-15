/**
 * gears.ts — geometry for the Movement's gear train (pure functions, no React).
 *
 * Gear vocabulary, simply:
 *   n   = number of teeth
 *   m   = module: tooth size. Two gears only mesh if they have the same module.
 *   rp  = pitch radius = m·n/2 — the imaginary circles that "roll" on each other
 *   ra  = tip radius   = rp + m        (outer end of the teeth)
 *   rf  = root radius  = rp − 1.25·m   (bottom of the gaps)
 *   p   = 2π/n         — angle between neighbouring teeth
 * Two meshing gears sit (m·(n1+n2)/2) apart, turn in opposite directions, and their speeds are in the
 * inverse ratio of their teeth: ω2 = −ω1·n1/n2 (a small gear spins faster).
 * To make the teeth interlock visually, gear 1 starts with a tooth pointing at gear 2 (angle α) and
 * gear 2 starts with a GAP pointing back at gear 1: phase α + π − π/n2.
 */

export interface GearSpec {
  n: number;
  m: number;
}

/** SVG path of a gear centred on (0, 0): trapezoid teeth joined by arcs along the root circle. */
export function gearPath({ n, m }: GearSpec): string {
  const rp = (m * n) / 2;
  const ra = rp + m;
  const rf = rp - 1.25 * m;
  const p = (2 * Math.PI) / n;
  const pt = (r: number, a: number) => `${(r * Math.cos(a)).toFixed(2)} ${(r * Math.sin(a)).toFixed(2)}`;
  let d = '';
  for (let i = 0; i < n; i++) {
    const c = i * p;
    const rootL = c - 0.25 * p;
    const tipL = c - 0.12 * p;
    const tipR = c + 0.12 * p;
    const rootR = c + 0.25 * p;
    d += i === 0 ? `M${pt(rf, rootL)}` : `L${pt(rf, rootL)}`;
    d += `L${pt(ra, tipL)}L${pt(ra, tipR)}L${pt(rf, rootR)}`;
    // Arc along the root circle to the next tooth.
    d += `A${rf.toFixed(2)} ${rf.toFixed(2)} 0 0 1 ${pt(rf, c + 0.75 * p)}`;
  }
  return d + 'Z';
}

export function pitchRadius({ n, m }: GearSpec): number {
  return (m * n) / 2;
}

/** Centre of gear 2 meshing with gear 1 at angle α (radians). */
export function meshCentre(c1: { x: number; y: number }, g1: GearSpec, g2: GearSpec, alpha: number) {
  const dist = (g1.m * (g1.n + g2.n)) / 2;
  return { x: c1.x + dist * Math.cos(alpha), y: c1.y + dist * Math.sin(alpha) };
}

/** Starting rotation (degrees) for gear 2 so its teeth fall into gear 1's gaps. */
export function meshPhaseDeg(alpha: number, g2: GearSpec): number {
  return ((alpha + Math.PI - Math.PI / g2.n) * 180) / Math.PI;
}
