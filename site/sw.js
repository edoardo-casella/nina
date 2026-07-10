// Cache-first per il guscio, network-first per i dati.
// In rada senza rete la pagina si apre lo stesso e mostra l'ultimo briefing scaricato,
// con la sua data bene in vista. Un dato vecchio dichiarato e' utile; un dato vecchio
// spacciato per fresco e' pericoloso.
const SHELL = "nina-shell-v1";
const DATA = "nina-data-v1";
const FILES = ["./", "./index.html", "./manifest.json"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks =>
    Promise.all(ks.filter(k => k !== SHELL && k !== DATA).map(k => caches.delete(k)))
  ).then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;

  if (url.pathname.includes("/data/")) {
    e.respondWith(
      fetch(e.request).then(r => {
        const copy = r.clone();
        caches.open(DATA).then(c => c.put(e.request, copy));
        return r;
      }).catch(() => caches.match(e.request))
    );
    return;
  }
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
