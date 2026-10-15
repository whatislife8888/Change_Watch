/*
 * sw.js — the service worker that makes ChangeWatch an installable, offline-tolerant web app.
 *
 * A service worker is a small script the browser runs in the background, between the page and the
 * network. We use it for one job: keep the app's *shell* (HTML, JS, CSS, fonts, icons) on the phone so
 * the app opens instantly from the home screen, and still opens with no connection.
 *
 * Rules (chosen so a deploy can never leave you stuck on an old version):
 *   - /api, /rss, /demo, /healthz, /bot: never touched. Live data and the SSE stream always go to the server.
 *   - Page navigations: network first; the cached index.html is used only when the network fails.
 *   - /assets/*: cache first. Vite puts a content hash in these file names, so a new deploy has new
 *     names and an old cached file can never be served by mistake.
 *   - Precache: the build writes /asset-manifest.json (every built file + a version). We cache the whole
 *     list on install, and re-check it after each online page load so a new deploy is cached too
 *     (files from older builds are deleted).
 *   - Icons, manifest, favicon: stale-while-revalidate (serve the cached copy, refresh in the background).
 */
const CACHE = 'changewatch-shell-v1';
const SHELL = ['/', '/manifest.webmanifest', '/icons/icon-192.png', '/favicon.svg'];
const BYPASS = ['/api/', '/rss/', '/demo/', '/healthz', '/bot', '/robots.txt', '/asset-manifest.json'];

/** Cache every file of the current build (once per build version). */
async function precacheBuild() {
  try {
    const response = await fetch('/asset-manifest.json', { cache: 'no-store' });
    if (!response.ok) return;
    const { version, files } = await response.json();
    const cache = await caches.open(CACHE);
    const known = await cache.match('/__build-version');
    if (known && (await known.text()) === version) return;
    await cache.addAll(files);
    // Remove hashed files that belong to older builds.
    const keep = new Set(files);
    for (const request of await cache.keys()) {
      const path = new URL(request.url).pathname;
      if (path.startsWith('/assets/') && !keep.has(path)) await cache.delete(request);
    }
    await cache.put('/__build-version', new Response(version));
  } catch {
    /* offline or dev server (no manifest): nothing to do */
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(precacheBuild).then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (BYPASS.some((prefix) => url.pathname.startsWith(prefix))) return;

  // App pages (/, /pages/12, /settings...): always try the network so you get the latest version.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Only remember real app pages (never an error page shown during a deploy).
          if (response.ok && (response.headers.get('content-type') || '').includes('text/html')) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put('/', copy));
            event.waitUntil(precacheBuild());
          }
          return response;
        })
        .catch(() => caches.match('/').then((cached) => cached || offlinePage())),
    );
    return;
  }

  // Hashed build files never change: cache first.
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      })),
    );
    return;
  }

  // Everything else from our origin (icons, manifest, favicon): stale-while-revalidate.
  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      }).catch(() => cached);
      return cached || network;
    }),
  );
});

function offlinePage() {
  const html = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    + '<title>ChangeWatch</title><body style="margin:0;display:grid;place-items:center;min-height:100vh;background:#0B1411;'
    + 'color:#ECE7DC;font:16px/1.5 system-ui,sans-serif;text-align:center;padding:24px">'
    + '<div><h1 style="font:300 32px Georgia,serif;margin:0 0 8px">You’re offline</h1>'
    + '<p style="color:#A9B2AE;margin:0">ChangeWatch keeps checking your pages on the server. Reconnect to see the latest.</p></div>';
  return new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
}
