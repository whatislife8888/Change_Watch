/**
 * Modal.tsx — a dialog box over the page (used to confirm deletes).
 * Escape or clicking the backdrop closes it; focus moves into the dialog when it opens and returns to
 * the previously focused element when it closes, so keyboard users never get lost.
 */
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { dur, easeOut } from '../../design/motion';
import s from './ui.module.css';

export function Modal({
  open, onClose, title, children, actions,
}: { open: boolean; onClose: () => void; title: string; children?: ReactNode; actions?: ReactNode }) {
  const titleId = useId();
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    // Focus the first focusable element in the dialog.
    requestAnimationFrame(() => {
      const first = boxRef.current?.querySelector<HTMLElement>('button, [href], input, select, textarea');
      first?.focus();
    });
    return () => {
      document.removeEventListener('keydown', onKey);
      previous?.focus?.();
    };
  }, [open, onClose]);

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className={s.backdrop}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: dur.press }}
          onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
          <motion.div
            ref={boxRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className={s.modal}
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: dur.ui, ease: easeOut }}
          >
            <h2 id={titleId} className={s.modalTitle}>{title}</h2>
            {children}
            {actions && <div className={s.modalActions}>{actions}</div>}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
