const CACHE_NAME = "vyapara-v2";
const SHELL = [
  "/offline",
  "/static/css/app.css",
  "/static/js/common.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css",
  "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"
];

const SENSITIVE_PATHS = [
  "/api/",
  "/invoices",
  "/reports",
  "/accounts",
  "/parties",
  "/purchases",
  "/sales",
  "/settings"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)).catch(() => undefined));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))));
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || SENSITIVE_PATHS.some((path) => url.pathname.startsWith(path))) {
    event.respondWith(fetch(req).catch(() => caches.match("/offline")));
    return;
  }
  if (req.destination === "style" || req.destination === "script" || req.destination === "image" || url.pathname.startsWith("/static/")) {
    event.respondWith(caches.match(req).then((cached) => cached || fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
      return res;
    })));
    return;
  }
  event.respondWith(fetch(req).catch(() => caches.match(req).then((cached) => cached || caches.match("/offline"))));
});
