/**
 * hooks.ts — one TanStack Query hook per API endpoint.
 *
 * TanStack Query keeps a cache of server data keyed by "query keys" (e.g. ['watches']). Components
 * call a hook and get { data, isLoading, error }; the library handles loading states, caching,
 * background refetching and de-duplicating identical requests. Mutations (POST/PATCH/DELETE) then
 * "invalidate" the affected keys so the screen refreshes with fresh data.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from './client';
import type {
  ActivityItem, AdminStats, CheckLogItem, CheckQueued, CompareResult, NumbersOut, OverviewStats, SnapshotDetail,
  SnapshotItem, UrlPreview, User, WatchCreate, WatchDetail, WatchPatch, WatchSummary,
} from './types';

export const keys = {
  me: ['me'] as const,
  watches: ['watches'] as const,
  watch: (id: number) => ['watch', id] as const,
  snapshots: (id: number) => ['snapshots', id] as const,
  snapshot: (id: number) => ['snapshot', id] as const,
  compare: (id: number, a: number, b: number) => ['compare', id, a, b] as const,
  checks: (id: number) => ['checks', id] as const,
  numbers: (id: number) => ['numbers', id] as const,
  overview: ['overview'] as const,
  activity: (filter: string) => ['activity', filter] as const,
  admin: ['admin'] as const,
  settings: ['settings'] as const,
};

// ---------- auth ----------

/** The logged-in user, or null when logged out. Never redirects. */
export function useMe() {
  return useQuery<User | null>({
    queryKey: keys.me,
    queryFn: async () => {
      try {
        return await api<User>('/api/auth/me', { allow401: true });
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return null;
        throw err;
      }
    },
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) => api<User>('/api/auth/login', { method: 'POST', body }),
    onSuccess: (user) => {
      qc.clear();
      qc.setQueryData(keys.me, user);
    },
  });
}

export function useSignup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string; display_name: string }) =>
      api<User>('/api/auth/signup', { method: 'POST', body }),
    onSuccess: (user) => {
      qc.clear();
      qc.setQueryData(keys.me, user);
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
    onSuccess: () => {
      qc.clear();
      qc.setQueryData(keys.me, null);
    },
  });
}

// ---------- url preview ----------

export function previewUrl(url: string, signal?: AbortSignal) {
  return api<UrlPreview>('/api/url/preview', { method: 'POST', body: { url }, signal });
}

// ---------- watches ----------

export function useWatches() {
  return useQuery({ queryKey: keys.watches, queryFn: () => api<WatchSummary[]>('/api/watches') });
}

export function useOverview() {
  return useQuery({ queryKey: keys.overview, queryFn: () => api<OverviewStats>('/api/stats/overview') });
}

export function useWatch(id: number) {
  return useQuery({ queryKey: keys.watch(id), queryFn: () => api<WatchDetail>(`/api/watches/${id}`), enabled: id > 0 });
}

export function useCreateWatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WatchCreate) => api<WatchDetail>('/api/watches', { method: 'POST', body }),
    onSuccess: (watch) => {
      qc.setQueryData(keys.watch(watch.id), watch);
      void qc.invalidateQueries({ queryKey: keys.watches });
      void qc.invalidateQueries({ queryKey: keys.overview });
    },
  });
}

/** PATCH a watch. Pausing/resuming is optimistic: the dial dims immediately, and rolls back on error. */
export function useUpdateWatch(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WatchPatch) => api<WatchDetail>(`/api/watches/${id}`, { method: 'PATCH', body }),
    onMutate: async (body) => {
      if (body.paused === undefined) return undefined;
      await qc.cancelQueries({ queryKey: keys.watches });
      const previous = qc.getQueryData<WatchSummary[]>(keys.watches);
      qc.setQueryData<WatchSummary[]>(keys.watches, (list) => list?.map((w) => (w.id === id ? { ...w, paused: !!body.paused } : w)));
      return { previous };
    },
    onError: (_err, _body, ctx) => {
      if (ctx?.previous) qc.setQueryData(keys.watches, ctx.previous);
    },
    onSuccess: (watch) => {
      qc.setQueryData(keys.watch(id), watch);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: keys.watches });
      void qc.invalidateQueries({ queryKey: keys.overview });
    },
  });
}

export function useDeleteWatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/api/watches/${id}`, { method: 'DELETE' }),
    onSuccess: (_d, id) => {
      qc.setQueryData<WatchSummary[]>(keys.watches, (list) => list?.filter((w) => w.id !== id));
      qc.removeQueries({ queryKey: keys.watch(id) });
      void qc.invalidateQueries({ queryKey: keys.overview });
    },
  });
}

export function useCheckNow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<CheckQueued>(`/api/watches/${id}/check`, { method: 'POST' }),
    onSuccess: (_d, id) => {
      qc.setQueryData<WatchSummary[]>(keys.watches, (list) => list?.map((w) => (w.id === id ? { ...w, is_queued: true } : w)));
      qc.setQueryData<WatchDetail>(keys.watch(id), (w) => (w ? { ...w, is_queued: true } : w));
    },
  });
}

export function useSnapshots(id: number) {
  return useQuery({ queryKey: keys.snapshots(id), queryFn: () => api<SnapshotItem[]>(`/api/watches/${id}/snapshots?limit=100`), enabled: id > 0 });
}

export function useSnapshot(id: number | null) {
  return useQuery({ queryKey: keys.snapshot(id ?? 0), queryFn: () => api<SnapshotDetail>(`/api/snapshots/${id}`), enabled: !!id });
}

export function useCompare(id: number, a: number | null, b: number | null) {
  return useQuery({
    queryKey: keys.compare(id, a ?? 0, b ?? 0),
    queryFn: () => api<CompareResult>(`/api/watches/${id}/compare?a=${a}&b=${b}`),
    enabled: !!a && !!b && a !== b,
    staleTime: Infinity,
  });
}

export function useChecks(id: number) {
  return useQuery({ queryKey: keys.checks(id), queryFn: () => api<CheckLogItem[]>(`/api/watches/${id}/checks?limit=100`), enabled: id > 0 });
}

export function useNumbers(id: number, enabled = true) {
  return useQuery({ queryKey: keys.numbers(id), queryFn: () => api<NumbersOut>(`/api/watches/${id}/numbers`), enabled: id > 0 && enabled });
}

export function useDeleteRule(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (index: number) => api<WatchDetail>(`/api/watches/${id}/volatile-rules/${index}`, { method: 'DELETE' }),
    onSuccess: (w) => qc.setQueryData(keys.watch(id), w),
  });
}

export function useRegenerateRss(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<{ rss_url: string }>(`/api/watches/${id}/rss/regenerate`, { method: 'POST' }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.watch(id) }),
  });
}

export function useShare(id: number) {
  return useMutation({ mutationFn: () => api<{ template_url: string; token: string }>(`/api/watches/${id}/share`, { method: 'POST' }) });
}

// ---------- activity / admin ----------

export function useActivity(filter: { watchId?: number; kind?: string } = {}) {
  const params = new URLSearchParams({ limit: '100' });
  if (filter.watchId) params.set('watch_id', String(filter.watchId));
  if (filter.kind) params.set('kind', filter.kind);
  const qs = params.toString();
  return useQuery({ queryKey: keys.activity(qs), queryFn: () => api<ActivityItem[]>(`/api/activity?${qs}`) });
}

export function useAdminStats(enabled: boolean) {
  return useQuery({ queryKey: keys.admin, queryFn: () => api<AdminStats>('/api/admin/stats'), enabled, refetchInterval: 10_000 });
}
