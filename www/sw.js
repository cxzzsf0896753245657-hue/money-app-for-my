// 離線快取：頁面本體與 prices.json 都「先連網、失敗才用快取」，確保網頁版每次都拿到最新版；
// 圖示等靜態檔先用快取。改版時不需要再手動改 VER。
const VER = "v3";
const SHELL = ["./", "./index.html", "./manifest.webmanifest", "./icon-192.png", "./icon-512.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(VER).then(c => c.addAll(SHELL))); self.skipWaiting(); });
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VER).map(k => caches.delete(k)))));
  self.clients.claim();
});
const netFirst = req => fetch(req).then(res => {
  if (res.ok) { const copy = res.clone(); caches.open(VER).then(c => c.put(req, copy)); }
  return res;
}).catch(() => caches.match(req, { ignoreSearch: true }));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin) return;
  if (e.request.mode === "navigate" || u.pathname.endsWith("/") || u.pathname.endsWith(".html") || u.pathname.endsWith("prices.json")) {
    e.respondWith(netFirst(e.request));
    return;
  }
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request).then(res => {
    if (res.ok) { const copy = res.clone(); caches.open(VER).then(c => c.put(e.request, copy)); }
    return res;
  })));
});
