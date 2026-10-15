/**
 * Offline.tsx — what the app shows when the phone has no connection.
 *
 * - OfflineScreen: shown instead of a page when we can't even ask the server who you are (for example,
 *   the app was opened from the home screen in airplane mode). It is NOT a logout: the moment the
 *   connection returns, TanStack Query refetches and the real page appears.
 * - OfflineBanner: a thin bar when the connection drops while you're using the app; what's on screen
 *   stays readable, and it refreshes itself on reconnect.
 */
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useSyncExternalStore } from 'react';
import { Mark } from '../dial/Mark';
import { Button } from '../ui/Button';
import s from './Offline.module.css';

/** True while the browser reports a network connection. */
function useOnline(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      window.addEventListener('online', onChange);
      window.addEventListener('offline', onChange);
      return () => {
        window.removeEventListener('online', onChange);
        window.removeEventListener('offline', onChange);
      };
    },
    () => navigator.onLine,
    () => true,
  );
}

export function OfflineScreen() {
  const qc = useQueryClient();
  // Retry on our own every few seconds as well as on the browser's "online" event, because some phones
  // (and network emulators) don't reliably fire that event when the connection returns.
  useEffect(() => {
    const retry = () => void qc.refetchQueries({ queryKey: ['me'] });
    const timer = window.setInterval(retry, 4000);
    window.addEventListener('online', retry);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('online', retry);
    };
  }, [qc]);
  return (
    <main className={s.screen}>
      <Mark size={56} />
      <h1 className={s.title}>You're offline</h1>
      <p className={s.body}>ChangeWatch keeps checking your pages on the server. Reconnect to see the latest.</p>
      <Button variant="secondary" onClick={() => void qc.refetchQueries()}>Try again</Button>
    </main>
  );
}

export function OfflineBanner() {
  const online = useOnline();
  if (online) return null;
  return (
    <div className={s.banner} role="status">
      You're offline. This screen refreshes when you reconnect.
    </div>
  );
}
