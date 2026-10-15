/**
 * Tabs.tsx — a tab bar (role="tablist") with a blued underline that slides to the active tab.
 * Arrow keys move between tabs. The caller renders the matching panel.
 */
import { motion } from 'motion/react';
import { useId, useRef, type KeyboardEvent } from 'react';
import { spring, usePrefersReducedMotion } from '../../design/motion';
import s from './ui.module.css';

export function Tabs<T extends string>({
  tabs, value, onChange, label,
}: { tabs: { value: T; label: string }[]; value: T; onChange: (v: T) => void; label: string }) {
  const id = useId();
  const reduced = usePrefersReducedMotion();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(e: KeyboardEvent, i: number) {
    let next = -1;
    if (e.key === 'ArrowRight') next = (i + 1) % tabs.length;
    if (e.key === 'ArrowLeft') next = (i - 1 + tabs.length) % tabs.length;
    if (next >= 0) {
      e.preventDefault();
      onChange(tabs[next].value);
      refs.current[next]?.focus();
    }
  }

  return (
    <div className={s.tabs} role="tablist" aria-label={label}>
      {tabs.map((t, i) => (
        <button
          key={t.value}
          ref={(el) => { refs.current[i] = el; }}
          role="tab"
          type="button"
          id={`tab-${t.value}`}
          aria-selected={t.value === value}
          aria-controls={`panel-${t.value}`}
          tabIndex={t.value === value ? 0 : -1}
          className={s.tab}
          onClick={() => onChange(t.value)}
          onKeyDown={(e) => onKeyDown(e, i)}
        >
          {t.label}
          {t.value === value && (
            <motion.span layoutId={`tabline-${id}`} className={s.tabLine} transition={reduced ? { duration: 0 } : spring} />
          )}
        </button>
      ))}
    </div>
  );
}
