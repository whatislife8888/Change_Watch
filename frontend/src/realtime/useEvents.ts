/**
 * useEvents.ts — keeps the screen live using Server-Sent Events from /api/events.
 *
 * One EventSource per logged-in tab. Each event updates the TanStack Query cache (or asks it to refetch),
 * so every component showing that data re-renders by itself:
 *   queue          → the Movement's gears (stored in a tiny shared store, see `useQueueStats`)
 *   check_started  → mark those dials as running (lume arc)
 *   check_finished → refresh the watch (hand re-syncs to the new schedule), soft tick sound
 *   change         → re-engrave that dial, toast "X changed: summary" with a Compare action, chime
 *   status_change  → refresh the watch (jewel colour + status line)
 * If the stream drops, the browser reconnects; after repeated failures we fall back to polling every 30 s.
 */
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useSyncExternalStore } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { API_BASE } from '../api/client';
import { keys } from '../api/hooks';
import type { QueueStats, WatchSummary } from '../api/types';
import { chime, tick } from '../lib/sound';

// ---- a tiny external store for queue stats and per-watch "engrave" counters ----
let queueStats: QueueStats = { running: 0, waiting: 0, workers: 3, workers_busy: [false, false, false], completed: 0 };
const engraveCounters = new Map<number, number>();
const listeners = new Set<() => void>();
let version = 0;

function emit() {
  version += 1;
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Live queue numbers for the Movement. */
export function useQueueStats(): QueueStats {
  return useSyncExternalStore(subscribe, () => queueStats);
}

/** A number that increases every time this watch's page changes (the Dial re-engraves on change). */
export function useEngraveKey(watchId: number): number {
  useSyncExternalStore(subscribe, () => version);
  return engraveCounters.get(watchId) ?? 0;
}

/** Connect to the SSE stream while `enabled` (i.e. logged in). Call once, near the top of the app. */
export function useEvents(enabled: boolean) {
  const qc = useQueryClient();
  const navigate = useNavigate();

  useEffect(() => {
    if (!enabled) return;
    let source: EventSource | null = null;
    let failures = 0;
    let pollTimer: number | undefined;
    let retryTimer: number | undefined;
    let closed = false;

    const refreshWatch = (id: number) => {
      void qc.invalidateQueries({ queryKey: keys.watches });
      void qc.invalidateQueries({ queryKey: keys.watch(id) });
      void qc.invalidateQueries({ queryKey: keys.overview });
      void qc.invalidateQueries({ queryKey: keys.checks(id) });
    };

    const setRunning = (ids: number[], running: boolean) => {
      qc.setQueryData<WatchSummary[]>(keys.watches, (list) =>
        list?.map((w) => (ids.includes(w.id) ? { ...w, is_running: running, is_queued: false } : w)));
    };

    const connect = () => {
      source = new EventSource(`${API_BASE}/api/events`, { withCredentials: true });
      source.addEventListener('open', () => { failures = 0; });
      source.addEventListener('queue', (e) => {
        queueStats = JSON.parse((e as MessageEvent).data) as QueueStats;
        emit();
      });
      source.addEventListener('check_started', (e) => {
        const { watch_ids } = JSON.parse((e as MessageEvent).data) as { watch_ids: number[] };
        setRunning(watch_ids, true);
        watch_ids.forEach((id) => qc.setQueryData(keys.watch(id), (w: object | undefined) => (w ? { ...w, is_running: true } : w)));
      });
      source.addEventListener('check_finished', (e) => {
        const data = JSON.parse((e as MessageEvent).data) as { watch_id: number };
        setRunning([data.watch_id], false);
        refreshWatch(data.watch_id);
        tick();
      });
      source.addEventListener('status_change', (e) => {
        const data = JSON.parse((e as MessageEvent).data) as { watch_id: number };
        refreshWatch(data.watch_id);
      });
      source.addEventListener('change', (e) => {
        const data = JSON.parse((e as MessageEvent).data) as {
          watch_id: number; snapshot_id: number; previous_snapshot_id: number | null; summary: string; name: string;
        };
        engraveCounters.set(data.watch_id, (engraveCounters.get(data.watch_id) ?? 0) + 1);
        emit();
        refreshWatch(data.watch_id);
        void qc.invalidateQueries({ queryKey: keys.snapshots(data.watch_id) });
        void qc.invalidateQueries({ queryKey: ['activity'] });
        chime();
        toast(`${data.name} changed`, {
          description: data.summary,
          duration: 9000,
          action: data.previous_snapshot_id
            ? { label: 'Compare', onClick: () => navigate(`/pages/${data.watch_id}/compare?a=${data.previous_snapshot_id}&b=${data.snapshot_id}`) }
            : undefined,
        });
      });
      source.onerror = () => {
        failures += 1;
        if (failures >= 4 && source) {
          // The stream keeps failing (e.g. a proxy that buffers SSE): stop it and poll instead.
          source.close();
          source = null;
          if (!pollTimer) {
            pollTimer = window.setInterval(() => {
              void qc.invalidateQueries({ queryKey: keys.watches });
              void qc.invalidateQueries({ queryKey: keys.overview });
            }, 30_000);
          }
          if (!closed) retryTimer = window.setTimeout(() => { failures = 0; connect(); }, 60_000);
        }
      };
    };

    connect();
    return () => {
      closed = true;
      source?.close();
      if (pollTimer) window.clearInterval(pollTimer);
      if (retryTimer) window.clearTimeout(retryTimer);
    };
  }, [enabled, qc, navigate]);
}
