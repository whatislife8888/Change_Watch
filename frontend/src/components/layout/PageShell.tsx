/**
 * PageShell.tsx — the frame around every logged-in page: skip link (keyboard users jump straight to
 * the content), the top bar, and a <main> landmark with consistent spacing.
 */
import type { ReactNode } from 'react';
import s from './layout.module.css';
import { TopBar } from './TopBar';

export function PageShell({ children, flush = false }: { children: ReactNode; flush?: boolean }) {
  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <TopBar />
      <main id="main" className={flush ? s.mainFlush : s.main} tabIndex={-1}>
        {flush ? children : <div className="container">{children}</div>}
      </main>
    </>
  );
}

/** Site footer (used on the landing page). */
export function Footer() {
  return (
    <footer className={s.footer}>
      <div className={`container ${s.footerInner}`}>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 18, color: 'var(--text)' }}>ChangeWatch</span>
        <span>Made by Kushagra Singhal</span>
        <a href="https://github.com/" target="_blank" rel="noreferrer">GitHub</a>
        <a href="/bot">About our crawler</a>
      </div>
    </footer>
  );
}
