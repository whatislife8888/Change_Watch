/**
 * useMedia.ts — React hook for a CSS media query, e.g. useMedia('(max-width: 760px)').
 * Used where layout decisions must happen in JavaScript (bottom navigation, toast position).
 */
import { useSyncExternalStore } from 'react';

export function useMedia(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mql = window.matchMedia(query);
      mql.addEventListener('change', onChange);
      return () => mql.removeEventListener('change', onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/** Phone-sized screens: where the bottom tab bar replaces the top navigation. */
export const PHONE = '(max-width: 760px)';
