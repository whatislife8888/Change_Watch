/**
 * watchStatus.ts — one place that decides how a watch's state is shown (jewel colour + word).
 */
import type { WatchSummary } from '../api/types';
import type { JewelStatus } from '../components/dial/Jewel';
import type { StatusKind } from '../components/ui/misc';

export function jewelFor(w: Pick<WatchSummary, 'status' | 'paused'>): JewelStatus {
  if (w.paused) return 'paused';
  if (w.status === 'ok' || w.status === 'error' || w.status === 'blocked') return w.status;
  return 'pending';
}

export function statusKindFor(w: Pick<WatchSummary, 'status' | 'paused' | 'is_running'>): StatusKind {
  if (w.paused) return 'paused';
  if (w.is_running) return 'running';
  if (w.status === 'ok' || w.status === 'error' || w.status === 'blocked') return w.status;
  return 'pending';
}

/** Short status line under a dial; empty when everything is fine (quiet by default). */
export function statusLine(w: WatchSummary): string | null {
  if (w.paused) return 'Paused';
  if (w.is_running) return 'Checking now';
  if (w.is_queued) return 'Check queued';
  if (w.status === 'pending') return 'First check coming up';
  if (w.status === 'blocked') return w.status_message?.includes('robots') ? 'Disallowed by robots.txt' : 'Blocked by a bot check';
  if (w.status === 'error') return w.status_message?.includes('region') ? "Picked region not found" : "Couldn't reach the page";
  return null;
}
