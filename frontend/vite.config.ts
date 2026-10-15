/**
 * vite.config.ts — dev server + build settings for the frontend.
 *
 * Why the proxy: in development the browser only ever talks to Vite on :5173. Vite forwards API,
 * RSS, demo, health and bot requests to the Python backend on :8000. Because the browser sees a
 * single origin, the session cookie just works and we need no CORS setup.
 *
 * The small `assetManifest` plugin lists every built file in dist/asset-manifest.json, so the service
 * worker (public/sw.js) can cache the whole app for offline use — including screens you haven't opened.
 */
import { createHash } from 'node:crypto';
import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';

const BACKEND = 'http://localhost:8000';

function assetManifest(): Plugin {
  return {
    name: 'changewatch-asset-manifest',
    apply: 'build',
    generateBundle(_options, bundle) {
      const files = Object.keys(bundle).filter((name) => name.startsWith('assets/')).map((name) => '/' + name).sort();
      // The version changes whenever any file name changes (names contain content hashes).
      const version = createHash('sha256').update(files.join('|')).digest('hex').slice(0, 12);
      this.emitFile({ type: 'asset', fileName: 'asset-manifest.json', source: JSON.stringify({ version, files }) });
    },
  };
}

export default defineConfig({
  plugins: [react(), assetManifest()],
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
