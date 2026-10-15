/**
 * useSpecular.ts — makes a dial respond to the pointer like polished metal under a lamp.
 *
 * It sets two CSS variables on the element as the pointer moves:
 *   --mx / --my  : where the soft highlight sits (a radial gradient in Dial.module.css reads them)
 *   --rx / --ry  : a small 3D tilt toward the pointer (max 6 degrees)
 * Writing CSS variables directly (instead of React state) avoids re-rendering on every mouse move,
 * which keeps a dashboard of 30 dials smooth. Disabled with reduced motion.
 */
import { useCallback, useRef } from 'react';
import { usePrefersReducedMotion } from '../../design/motion';

const MAX_TILT = 6;

export function useSpecular<T extends HTMLElement>(enabled = true) {
  const ref = useRef<T | null>(null);
  const frame = useRef<number>(0);
  const reduced = usePrefersReducedMotion();
  const active = enabled && !reduced;

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    const el = ref.current;
    if (!el || !active || e.pointerType === 'touch') return;
    const rect = el.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width; // 0..1
    const y = (e.clientY - rect.top) / rect.height;
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      el.style.setProperty('--mx', `${(x * 100).toFixed(1)}%`);
      el.style.setProperty('--my', `${(y * 100).toFixed(1)}%`);
      el.style.setProperty('--rx', `${((0.5 - y) * 2 * MAX_TILT).toFixed(2)}deg`);
      el.style.setProperty('--ry', `${((x - 0.5) * 2 * MAX_TILT).toFixed(2)}deg`);
    });
  }, [active]);

  const onPointerLeave = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    cancelAnimationFrame(frame.current);
    el.style.setProperty('--rx', '0deg');
    el.style.setProperty('--ry', '0deg');
    el.style.setProperty('--mx', '32%');
    el.style.setProperty('--my', '24%');
  }, []);

  return { ref, handlers: active ? { onPointerMove, onPointerLeave } : {} };
}
