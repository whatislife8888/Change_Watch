/**
 * SegmentedControl.tsx — a row of mutually exclusive options (e.g. check interval 15m / 1h / 24h).
 *
 * Accessibility: it's a radiogroup; arrow keys move the selection, and only the selected option is
 * in the Tab order (the standard "roving tabindex" pattern).
 * The raised thumb slides between options using a shared Motion layoutId.
 */
import { motion } from 'motion/react';
import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react';
import { spring, usePrefersReducedMotion } from '../../design/motion';
import s from './ui.module.css';

export interface SegmentOption<T extends string | number> {
  value: T;
  label: ReactNode;
  ariaLabel?: string;
}

export function SegmentedControl<T extends string | number>({
  options, value, onChange, label,
}: { options: SegmentOption<T>[]; value: T; onChange: (v: T) => void; label: string }) {
  const groupId = useId();
  const reduced = usePrefersReducedMotion();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(e: KeyboardEvent, index: number) {
    let next = -1;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (index + 1) % options.length;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (index - 1 + options.length) % options.length;
    if (next >= 0) {
      e.preventDefault();
      onChange(options[next].value);
      refs.current[next]?.focus();
    }
  }

  return (
    <div className={s.segmented} role="radiogroup" aria-label={label}>
      {options.map((opt, i) => {
        const checked = opt.value === value;
        return (
          <button
            key={String(opt.value)}
            ref={(el) => { refs.current[i] = el; }}
            type="button"
            role="radio"
            aria-checked={checked}
            aria-label={opt.ariaLabel}
            tabIndex={checked ? 0 : -1}
            className={s.segment}
            onClick={() => onChange(opt.value)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {checked && (
              <motion.span
                layoutId={`seg-${groupId}`}
                className={s.segmentThumb}
                transition={reduced ? { duration: 0 } : spring}
              />
            )}
            <span className={s.segmentLabel}>{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}
