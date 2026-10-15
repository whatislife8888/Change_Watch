/**
 * useNow.ts — re-render every `ms` milliseconds so relative times ("4 minutes ago") stay correct.
 */
import { useEffect, useState } from 'react';

export function useNow(ms = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(id);
  }, [ms]);
  return now;
}
