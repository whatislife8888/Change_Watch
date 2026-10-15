/**
 * Menu.tsx — a small pop-up action menu (e.g. a dial's Check now / Pause / Edit / Delete).
 * Opens on click or Enter, arrow keys move between items, Escape or a click outside closes it.
 */
import clsx from 'clsx';
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { dur, easeOut } from '../../design/motion';
import s from './ui.module.css';

export interface MenuItem {
  label: string;
  icon?: ReactNode;
  onSelect: () => void;
  danger?: boolean;
  disabled?: boolean;
}

export function Menu({
  trigger, items, label, triggerClassName,
}: { trigger: ReactNode; items: MenuItem[]; label: string; triggerClassName?: string }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    requestAnimationFrame(() => itemRefs.current[0]?.focus());
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  function onMenuKey(e: KeyboardEvent) {
    const enabled = itemRefs.current.filter(Boolean) as HTMLButtonElement[];
    const i = enabled.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === 'Escape') { setOpen(false); e.stopPropagation(); }
    if (e.key === 'ArrowDown') { e.preventDefault(); enabled[(i + 1) % enabled.length]?.focus(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); enabled[(i - 1 + enabled.length) % enabled.length]?.focus(); }
    if (e.key === 'Tab') setOpen(false);
  }

  return (
    <div className={s.menuWrap} ref={wrapRef} onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        className={triggerClassName}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={(e) => { e.preventDefault(); setOpen((o) => !o); }}
      >
        {trigger}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            id={menuId}
            role="menu"
            className={s.menu}
            onKeyDown={onMenuKey}
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: dur.press, ease: easeOut }}
          >
            {items.map((item, i) => (
              <button
                key={item.label}
                ref={(el) => { itemRefs.current[i] = el; }}
                type="button"
                role="menuitem"
                disabled={item.disabled}
                className={clsx(s.menuItem, item.danger && s.menuItemDanger)}
                onClick={(e) => { e.preventDefault(); setOpen(false); item.onSelect(); }}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
