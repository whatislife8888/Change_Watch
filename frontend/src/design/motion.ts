/**
 * motion.ts — the same easing curves, durations and springs as tokens.css, but as JavaScript values
 * for the Motion library (which animates from JS, so it can't read CSS variables directly).
 *
 * Also exports `usePrefersReducedMotion`, which every animated component checks so the app respects
 * the operating system's "reduce motion" setting.
 */
import { useEffect, useState } from 'react';

/** Cubic-bezier easings as [x1, y1, x2, y2] arrays (Motion's format). */
export const easeOut = [0.22, 1, 0.36, 1] as const;
export const easeMech = [0.65, 0, 0.35, 1] as const;

/** Durations in seconds (Motion uses seconds; CSS tokens use ms). */
export const dur = {
  press: 0.16,
  ui: 0.28,
  route: 0.6,
  load: 0.9,
} as const;

/** The spring used for the loupe and dial tilt: stiff enough to feel precise, damped so it never wobbles. */
export const spring = { type: 'spring', stiffness: 300, damping: 30 } as const;

/**
 * React hook: true when the user has asked their OS to reduce motion.
 * Why a hook: the preference can change while the page is open, and components need to re-render.
 */
export function usePrefersReducedMotion(): boolean {
  const query = '(prefers-reduced-motion: reduce)';
  const [reduced, setReduced] = useState<boolean>(() =>
    typeof window !== 'undefined' ? window.matchMedia(query).matches : false,
  );
  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setReduced(mql.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);
  return reduced;
}
