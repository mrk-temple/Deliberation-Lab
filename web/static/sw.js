/* 解惑议事厅 · Service Worker
 * 目的：满足 PWA「可安装」（需注册带 fetch 处理的 SW）+ 离线时给一个外壳。
 * 策略：network-first（先网络、失败回退缓存）——刻意不做 cache-first，
 * 免得改了 app.js/style.css 后吃旧缓存（开发期那个老坑）。/api/* 一律直连不缓存。
 */
const CACHE = "council-shell-v1";
const SHELL = ["/", "/index.html", "/style.css", "/app.js",
               "/manifest.webmanifest",
               "/icons/icon-192.png", "/icons/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const { request } = e;
  const url = new URL(request.url);
  // 只接管同源 GET；API / SSE 流不碰
  if (request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  e.respondWith(
    fetch(request)
      .then((res) => {
        // 成功的同源响应顺手更新缓存，作为离线回退
        if (res && res.ok && res.type === "basic") {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(request, copy));
        }
        return res;
      })
      .catch(() => caches.match(request).then((hit) => hit || caches.match("/")))
  );
});
