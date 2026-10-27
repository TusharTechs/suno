/* SUNO service worker: the app opens offline, and the last brief's audio plays offline.
   - App shell: cache first, refreshed in the background.
   - Brief audio and sample audio: cache first (they never change once made).
   - API GETs: network first, fall back to the last cached answer (the app marks it as offline).
   - Writes (notes, answers, feedback) are never cached; the app queues notes itself in IndexedDB. */
const SHELL = "suno-shell-v3", MEDIA = "suno-media-v1", API = "suno-api-v1";
const SHELL_FILES = ["/", "/index.html", "/app.js", "/style.css", "/manifest.webmanifest", "/icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => ![SHELL, MEDIA, API].includes(k)).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/audio/") || url.pathname.startsWith("/samples/audio/")) {
    e.respondWith(caches.open(MEDIA).then(async (c) => {
      const hit = await c.match(req, { ignoreSearch: true });
      if (hit) return hit;
      const res = await fetch(req.url);  // full fetch (not a Range request) so the whole file is cached
      if (res.ok && res.status === 200) c.put(req.url, res.clone());
      return res;
    }));
    return;
  }
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(fetch(req).then((res) => {
      if (res.ok) caches.open(API).then((c) => c.put(req, res.clone()));
      return res;
    }).catch(() => caches.match(req).then((hit) => hit || new Response(JSON.stringify({ error: "offline" }), { status: 503, headers: { "Content-Type": "application/json" } }))));
    return;
  }
  e.respondWith(caches.match(req, { ignoreSearch: true }).then((hit) => {
    const net = fetch(req).then((res) => { if (res.ok) caches.open(SHELL).then((c) => c.put(req, res.clone())); return res; }).catch(() => hit || caches.match("/index.html"));
    return hit || net;
  }));
});
