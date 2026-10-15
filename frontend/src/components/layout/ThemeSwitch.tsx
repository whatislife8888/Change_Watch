/**
 * ThemeSwitch.tsx — toggles between Fumé (dark) and Opaline (light).
 * The icon is a half-filled circle, like a moon-phase complication.
 */
import { CircleHalf } from '@phosphor-icons/react';
import { usePrefs } from '../../lib/theme';
import s from './layout.module.css';

export function ThemeSwitch() {
  const { theme, setTheme } = usePrefs();
  const next = theme === 'fume' ? 'opaline' : 'fume';
  return (
    <button
      type="button"
      className={s.iconBtn}
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next === 'opaline' ? 'Opaline (light)' : 'Fumé (dark)'} theme`}
      title={theme === 'fume' ? 'Fumé theme' : 'Opaline theme'}
    >
      <CircleHalf size={22} weight="light" style={{ transform: theme === 'opaline' ? 'rotate(180deg)' : undefined, transition: 'transform 280ms var(--ease-out)' }} />
    </button>
  );
}
