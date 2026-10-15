/**
 * AuthLayout.tsx — shared frame for Login and Signup: the top bar, the form column, and a large dial
 * engraving itself on the right (showing the current time), so the first screen already feels like
 * the product.
 */
import type { ReactNode } from 'react';
import { TopBar } from '../components/layout/TopBar';
import { Dial } from '../components/dial/Dial';
import s from './Auth.module.css';

export function AuthLayout({ children, seedHint }: { children: ReactNode; seedHint?: string | null }) {
  // A stable seed for the decorative dial; if a URL was carried over, hash its characters into one.
  let seed = '5ea1c0de';
  if (seedHint) {
    let h = 2166136261;
    for (const ch of seedHint) h = Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0;
    seed = h.toString(16).padStart(8, '0');
  }
  return (
    <>
      <TopBar />
      <main id="main" className={`container ${s.wrap}`}>
        <div className={s.formCol}>{children}</div>
        <div className={s.dialCol}>
          <Dial seed={seed} size={380} clock engrave decorative interactive />
        </div>
      </main>
    </>
  );
}
