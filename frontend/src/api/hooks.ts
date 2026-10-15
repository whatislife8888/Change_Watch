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
import type { User } from './types';

export const keys = {
  me: ['me'] as const,
};

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
