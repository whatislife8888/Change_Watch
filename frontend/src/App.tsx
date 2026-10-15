/**
 * App.tsx — providers (data cache, router, theme) and the route table.
 *
 * Routes that need login are wrapped in <RequireAuth>; it waits for the "who am I" check and sends
 * logged-out visitors to /login?next=... . "/" shows the landing page when logged out and the
 * dashboard when logged in. Pages are lazy-loaded so the first screen downloads less JavaScript.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { lazy, Suspense, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { Toaster } from 'sonner';
import { useMe } from './api/hooks';
import { ApiError } from './api/client';
import { BottomNav } from './components/layout/BottomNav';
import { OfflineBanner, OfflineScreen } from './components/layout/Offline';
import { PrefsProvider, usePrefs } from './lib/theme';
import { PHONE, useMedia } from './lib/useMedia';
import { useEvents } from './realtime/useEvents';

const Landing = lazy(() => import('./pages/Landing'));
const Login = lazy(() => import('./pages/Login'));
const Signup = lazy(() => import('./pages/Signup'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const AddPage = lazy(() => import('./pages/AddPage'));
const PageDetail = lazy(() => import('./pages/PageDetail'));
const Compare = lazy(() => import('./pages/Compare'));
const Picker = lazy(() => import('./pages/Picker'));
const Settings = lazy(() => import('./pages/Settings'));
const Activity = lazy(() => import('./pages/Activity'));
const System = lazy(() => import('./pages/System'));
const ImportTemplate = lazy(() => import('./pages/ImportTemplate'));
const NotFound = lazy(() => import('./pages/NotFound'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: true, staleTime: 15_000, retry: 1 },
  },
});

/**
 * Who is using the app right now? 'offline' means we couldn't reach the server to find out — that is
 * NOT the same as logged out, so we must not send the user to the login page.
 */
function useAuthState(): 'loading' | 'in' | 'out' | 'offline' {
  const { data: user, isPending, fetchStatus, error } = useMe();
  if (user) return 'in';
  if (error instanceof ApiError && error.code === 'network') return 'offline';
  if (isPending && fetchStatus === 'paused') return 'offline'; // the browser says there's no network
  if (isPending) return 'loading';
  return 'out';
}

/** Shows children only to logged-in users. */
function RequireAuth({ children }: { children: ReactNode }) {
  const state = useAuthState();
  const location = useLocation();
  if (state === 'loading') return null;
  if (state === 'offline') return <OfflineScreen />;
  if (state === 'out') return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  return <>{children}</>;
}

/** "/" — dashboard when logged in, landing page otherwise. */
function Home() {
  const state = useAuthState();
  if (state === 'loading') return null;
  if (state === 'offline') return <OfflineScreen />;
  return state === 'in' ? <Dashboard /> : <Landing />;
}

/** Logged-in users visiting /login or /signup go straight home. */
function GuestOnly({ children }: { children: ReactNode }) {
  const state = useAuthState();
  if (state === 'loading') return null;
  if (state === 'in') return <Navigate to="/" replace />;
  return <>{children}</>;
}

/** Opens the live SSE connection whenever someone is logged in. */
function LiveEvents() {
  const { data: user } = useMe();
  useEvents(!!user);
  return null;
}

function ThemedToaster() {
  const { theme } = usePrefs();
  const phone = useMedia(PHONE);
  // On phones toasts drop from the top, so they never cover the bottom tab bar or the thumb.
  return (
    <Toaster
      theme={theme === 'opaline' ? 'light' : 'dark'}
      position={phone ? 'top-center' : 'bottom-right'}
      mobileOffset={{ top: 'calc(env(safe-area-inset-top) + 68px)' }}
      closeButton={false}
      visibleToasts={phone ? 2 : 4}
      gap={10}
    />
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <PrefsProvider>
        <BrowserRouter>
          <Suspense fallback={null}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/login" element={<GuestOnly><Login /></GuestOnly>} />
              <Route path="/signup" element={<GuestOnly><Signup /></GuestOnly>} />
              <Route path="/pages/new" element={<RequireAuth><AddPage /></RequireAuth>} />
              <Route path="/pages/:id" element={<RequireAuth><PageDetail /></RequireAuth>} />
              <Route path="/pages/:id/compare" element={<RequireAuth><Compare /></RequireAuth>} />
              <Route path="/pages/:id/picker" element={<RequireAuth><Picker /></RequireAuth>} />
              <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
              <Route path="/activity" element={<RequireAuth><Activity /></RequireAuth>} />
              <Route path="/system" element={<RequireAuth><System /></RequireAuth>} />
              <Route path="/import/:token" element={<RequireAuth><ImportTemplate /></RequireAuth>} />
              <Route path="*" element={<RequireAuth><NotFound /></RequireAuth>} />
            </Routes>
          </Suspense>
          <BottomNav />
          <OfflineBanner />
          <LiveEvents />
          <ThemedToaster />
        </BrowserRouter>
      </PrefsProvider>
    </QueryClientProvider>
  );
}
