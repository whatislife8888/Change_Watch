/**
 * vite.config.ts — dev server + build settings for the frontend.
 *
 * Why the proxy: in development the browser only ever talks to Vite on :5173. Vite forwards API,
 * RSS, demo, health and bot requests to the Python backend on :8000. Because the browser sees a
 * single origin, the session cookie just works and we need no CORS setup.
 */
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const BACKEND = 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: false },
      '/rss': { target: BACKEND, changeOrigin: false },
      '/demo': { target: BACKEND, changeOrigin: false },
      '/healthz': { target: BACKEND, changeOrigin: false },
      '/bot': { target: BACKEND, changeOrigin: false },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
});
