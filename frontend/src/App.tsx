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
import { PrefsProvider, usePrefs } from './lib/theme';

const Login = lazy(() => import('./pages/Login'));
const Signup = lazy(() => import('./pages/Signup'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const NotFound = lazy(() => import('./pages/NotFound'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: true, staleTime: 15_000, retry: 1 },
  },
});

/** Shows children only to logged-in users. */
function RequireAuth({ children }: { children: ReactNode }) {
  const { data: user, isLoading } = useMe();
  const location = useLocation();
  if (isLoading) return null;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  return <>{children}</>;
}

/** "/" — dashboard when logged in, landing page otherwise. */
function Home() {
  const { data: user, isLoading } = useMe();
  if (isLoading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return <Dashboard />;
}

/** Logged-in users visiting /login or /signup go straight home. */
function GuestOnly({ children }: { children: ReactNode }) {
  const { data: user, isLoading } = useMe();
  if (isLoading) return null;
  if (user) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function ThemedToaster() {
  const { theme } = usePrefs();
  return <Toaster theme={theme === 'opaline' ? 'light' : 'dark'} position="bottom-right" closeButton={false} visibleToasts={4} gap={10} />;
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
              <Route path="*" element={<RequireAuth><NotFound /></RequireAuth>} />
            </Routes>
          </Suspense>
          <ThemedToaster />
        </BrowserRouter>
      </PrefsProvider>
    </QueryClientProvider>
  );
}
