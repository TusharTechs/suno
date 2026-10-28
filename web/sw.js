/* SUNO service worker: the app still opens offline, and the last brief's audio plays offline.
   - Page, scripts, styles: NETWORK FIRST, cache as fallback. Online, a visitor always gets the
     current version (cache-first served stale code after deploys); offline, the cached copy opens.
   - Brief audio and sample audio: cache first (they never change once made).
   - API GETs: network first, fall back to the last cached answer (the app marks it as offline).
   - Writes (notes, answers, feedback) are never cached; the app queues notes itself in IndexedDB. */
const VERSION = "v6";
const SHELL = "suno-shell-" + VERSION, MEDIA = "suno-media-v1", API = "suno-api-v1";
const SHELL_FILES = ["/", "/index.html", "/app.js", "/style.css", "/manifest.webmanifest", "/icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(SHELL_FILES.map((f) => new Request(f, { cache: "reload" }))))
    .then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    const old = (await caches.keys()).filter((k) => ![SHELL, MEDIA, API].includes(k));
    await Promise.all(old.map((k) => caches.delete(k)));
    await self.clients.claim();
    // Taking over from an older version: pages it served may be running old code, which has no
    // way to refresh itself. Reload them once, so nobody is left on a stale or mixed page.
    if (old.some((k) => k.startsWith("suno-shell-"))) {
      for (const c of await self.clients.matchAll({ type: "window" })) c.navigate(c.url).catch(() => {});
    }
  })());
});

const networkFirst = (req, cacheName, fallback) =>
  fetch(req).then((res) => {
    if (res.ok) { const copy = res.clone(); caches.open(cacheName).then((c) => c.put(req, copy)); }
    return res;
  }).catch(() => caches.match(req, { ignoreSearch: cacheName === SHELL }).then((hit) => hit || fallback()));

self.addEventListener("fetch", (e) => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/audio/") || url.pathname.startsWith("/samples/audio/")) {
    e.respondWith(caches.open(MEDIA).then(async (c) => {
      const hit = await c.match(req.url);
      if (hit) return hit;
      const res = await fetch(req.url);  // full fetch (not a Range request) so the whole file is cached
      if (res.ok && res.status === 200) c.put(req.url, res.clone());
      return res;
    }));
    return;
  }
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(networkFirst(req, API, () => new Response(JSON.stringify({ error: "offline" }), { status: 503, headers: { "Content-Type": "application/json" } })));
    return;
  }
  e.respondWith(networkFirst(req, SHELL, () => caches.match("/index.html")));
});
