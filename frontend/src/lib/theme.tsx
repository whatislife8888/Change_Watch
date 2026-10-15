/**
 * theme.tsx — which theme is active (Fumé or Opaline) and whether sound is on.
 *
 * The theme is applied by setting data-theme on <html>; tokens.css does the rest. The choice is
 * remembered in localStorage (a per-browser convenience; wrapped in try/catch because storage can be
 * unavailable in private windows).
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { setSoundEnabled } from './sound';

export type Theme = 'fume' | 'opaline';

interface Prefs {
  theme: Theme;
  setTheme: (t: Theme) => void;
  sound: boolean;
  setSound: (on: boolean) => void;
}

const PrefsContext = createContext<Prefs | null>(null);

function readPref(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writePref(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

/** Provides theme + sound preferences to the whole app. */
export function PrefsProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => (readPref('cw-theme') === 'opaline' ? 'opaline' : 'fume'));
  const [sound, setSoundState] = useState<boolean>(() => readPref('cw-sound') === 'on');

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    const meta = document.querySelector('meta[name="theme-color"]');
    meta?.setAttribute('content', theme === 'opaline' ? '#E9EAE6' : '#0B1411');
  }, [theme]);

  useEffect(() => {
    setSoundEnabled(sound);
  }, [sound]);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    writePref('cw-theme', t);
  }, []);

  const setSound = useCallback((on: boolean) => {
    setSoundState(on);
    writePref('cw-sound', on ? 'on' : 'off');
  }, []);

  const value = useMemo(() => ({ theme, setTheme, sound, setSound }), [theme, setTheme, sound, setSound]);
  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>;
}

export function usePrefs(): Prefs {
  const ctx = useContext(PrefsContext);
  if (!ctx) throw new Error('usePrefs must be used inside PrefsProvider');
  return ctx;
}
