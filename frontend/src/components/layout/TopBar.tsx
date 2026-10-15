/**
 * TopBar.tsx — the bar at the top of every logged-in page: wordmark, main navigation, sound and theme
 * toggles, the "Add page" button and the account menu. On phones the navigation folds into a menu.
 */
import { List, Plus } from '@phosphor-icons/react';
import clsx from 'clsx';
import { NavLink, useNavigate } from 'react-router-dom';
import { useLogout, useMe } from '../../api/hooks';
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
  const initial = (user?.display_name || user?.email || '?').charAt(0).toUpperCase();

  const navClass = ({ isActive }: { isActive: boolean }) => clsx(s.navLink, isActive && s.navActive);

  const accountItems = [
    { label: 'Settings', onSelect: () => navigate('/settings') },
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
        {user && (
          <nav className={s.nav} aria-label="Main">
            <NavLink to="/" end className={navClass}>Pages</NavLink>
            <NavLink to="/activity" className={navClass}>Activity</NavLink>
            <NavLink to="/settings" className={navClass}>Settings</NavLink>
          </nav>
        )}
        <div className={s.spacer} />
        <div className={s.tools}>
          <span className={s.hideMobile}><SoundToggle /></span>
          <ThemeSwitch />
          {user ? (
            <>
              <ButtonLink to="/pages/new" variant="primary" size="sm" aria-label="Add page">
                <Plus size={16} weight="regular" />
                <span className={s.addLabel}>Add page</span>
              </ButtonLink>
              <span className={s.mobileMenu}>
                <Menu
                  label="Open navigation"
                  triggerClassName={s.iconBtn}
                  trigger={<List size={22} weight="light" />}
                  items={[
                    { label: 'Pages', onSelect: () => navigate('/') },
                    { label: 'Activity', onSelect: () => navigate('/activity') },
                    ...accountItems,
                  ]}
                />
              </span>
              <span className={s.hideMobile}>
                <Menu label="Account" triggerClassName={s.avatarBtn} trigger={<span className={s.avatar}>{initial}</span>} items={accountItems} />
              </span>
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
