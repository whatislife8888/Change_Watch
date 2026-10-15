/**
 * TopBar.tsx — the bar at the top of every page: wordmark, main navigation, sound and theme toggles,
 * the "Add page" button and the account menu.
 *
 * On phones the main navigation moves to the bottom tab bar (BottomNav.tsx), so here we keep only the
 * wordmark, the theme switch and the account menu (which also holds the sound toggle). The bar pads
 * itself below the iPhone notch / status bar using the safe-area inset.
 */
import { Plus } from '@phosphor-icons/react';
import clsx from 'clsx';
import { NavLink, useNavigate } from 'react-router-dom';
import { useLogout, useMe } from '../../api/hooks';
import { unlockAudio } from '../../lib/sound';
import { usePrefs } from '../../lib/theme';
import { PHONE, useMedia } from '../../lib/useMedia';
import { Mark } from '../dial/Mark';
import { ButtonLink } from '../ui/Button';
import { Menu } from '../ui/Menu';
import s from './layout.module.css';
import { SoundToggle } from './SoundToggle';
import { ThemeSwitch } from './ThemeSwitch';

export function TopBar() {
  const { data: user } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const phone = useMedia(PHONE);
  const { sound, setSound } = usePrefs();
  const initial = (user?.display_name || user?.email || '?').charAt(0).toUpperCase();

  const navClass = ({ isActive }: { isActive: boolean }) => clsx(s.navLink, isActive && s.navActive);

  const accountItems = [
    ...(phone ? [{ label: sound ? 'Turn sounds off' : 'Turn sounds on', onSelect: () => { unlockAudio(); setSound(!sound); } }] : [{ label: 'Settings', onSelect: () => navigate('/settings') }]),
    ...(user?.is_admin ? [{ label: 'System', onSelect: () => navigate('/system') }] : []),
    { label: 'Log out', onSelect: () => logout.mutate(undefined, { onSuccess: () => navigate('/') }) },
  ];

  return (
    <header className={s.bar}>
      <div className={clsx('container', s.barInner)}>
        <NavLink to="/" className={s.brand} aria-label="ChangeWatch, all pages">
          <Mark size={30} />
          <span>ChangeWatch</span>
        </NavLink>
        {user && !phone && (
          <nav className={s.nav} aria-label="Main">
            <NavLink to="/" end className={navClass}>Pages</NavLink>
            <NavLink to="/activity" className={navClass}>Activity</NavLink>
            <NavLink to="/settings" className={navClass}>Settings</NavLink>
          </nav>
        )}
        <div className={s.spacer} />
        <div className={s.tools}>
          {!phone && <SoundToggle />}
          <ThemeSwitch />
          {user ? (
            <>
              {!phone && (
                <ButtonLink to="/pages/new" variant="primary" size="sm">
                  <Plus size={16} weight="regular" />
                  Add page
                </ButtonLink>
              )}
              <Menu label="Account" triggerClassName={s.avatarBtn} trigger={<span className={s.avatar}>{initial}</span>} items={accountItems} />
            </>
          ) : (
            <>
              <ButtonLink to="/login" variant="ghost" size="sm">Log in</ButtonLink>
              <ButtonLink to="/signup" variant="primary" size="sm">Sign up</ButtonLink>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
