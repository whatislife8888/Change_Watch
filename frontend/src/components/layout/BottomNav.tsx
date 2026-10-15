/**
 * BottomNav.tsx — the tab bar at the bottom of the screen on phones (like a native app).
 *
 * Why: on a phone the thumb reaches the bottom of the screen, and an installed web app has no browser
 * toolbar, so the main destinations live here: Pages, Activity, Add page and Settings. Each tab has an
 * icon AND a word (never an icon alone). It sits above the iPhone home indicator using the safe-area
 * inset, and only renders on phone-sized screens for logged-in users.
 */
import { GearSix, Plus, Pulse, Watch } from '@phosphor-icons/react';
import clsx from 'clsx';
import { NavLink } from 'react-router-dom';
import { useMe } from '../../api/hooks';
import { PHONE, useMedia } from '../../lib/useMedia';
import s from './BottomNav.module.css';

const TABS = [
  { to: '/', label: 'Pages', icon: Watch, end: true },
  { to: '/activity', label: 'Activity', icon: Pulse, end: false },
  { to: '/pages/new', label: 'Add', icon: Plus, end: true, primary: true },
  { to: '/settings', label: 'Settings', icon: GearSix, end: false },
];

export function BottomNav() {
  const { data: user } = useMe();
  const phone = useMedia(PHONE);
  if (!user || !phone) return null;
  return (
    <nav className={s.bar} aria-label="Main">
      {TABS.map(({ to, label, icon: Icon, end, primary }) => (
        <NavLink key={to} to={to} end={end} className={({ isActive }) => clsx(s.tab, isActive && s.active, primary && s.primary)}>
          <span className={s.icon} aria-hidden="true"><Icon size={primary ? 22 : 24} weight={primary ? 'regular' : 'light'} /></span>
          <span className={s.label}>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
