/**
 * install.ts — "Install ChangeWatch on this phone" support.
 *
 * - Registers the service worker (production builds only, so development never serves stale files).
 * - Android and desktop Chrome/Edge fire `beforeinstallprompt` when the app can be installed. We keep
 *   that event so Settings can show an "Install app" button that opens the browser's install dialog.
 * - iPhone Safari has no install event: users install with Share, then "Add to Home Screen", so we only
 *   detect iOS to show those instructions instead.
 * - `isStandalone()` is true when the app is already running from the home screen.
 */
import { useSyncExternalStore } from 'react';

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

let deferred: InstallPromptEvent | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

/** Call once at startup (main.tsx), before React renders, so the install event isn't missed. */
export function setupInstall(): void {
  if (typeof window === 'undefined') return;
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault(); // keep it for our own button instead of the browser's mini-bar
    deferred = e as InstallPromptEvent;
    notify();
  });
  window.addEventListener('appinstalled', () => {
    deferred = null;
    notify();
  });
  if (import.meta.env.PROD && 'serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch(() => { /* the app works fine without it */ });
    });
  }
}

export function isStandalone(): boolean {
  return window.matchMedia('(display-mode: standalone)').matches
    || (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

export function isIOS(): boolean {
  return /iphone|ipad|ipod/i.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1); // iPadOS reports as a Mac
}

/** True while the browser is offering an install dialog we can open. */
export function useCanInstall(): boolean {
  return useSyncExternalStore(
    (l) => { listeners.add(l); return () => listeners.delete(l); },
    () => deferred !== null,
  );
}

/** Open the browser's install dialog. Returns true if the user accepted. */
export async function promptInstall(): Promise<boolean> {
  if (!deferred) return false;
  await deferred.prompt();
  const choice = await deferred.userChoice;
  deferred = null;
  notify();
  return choice.outcome === 'accepted';
}
