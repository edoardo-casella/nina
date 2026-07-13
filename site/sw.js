// Guscio: stale-while-revalidate (si apre subito dalla cache, si aggiorna in
// background — niente client congelati sulla vecchia index.html).
// Dati: network-first con fallback cache. In rada senza rete la pagina si apre
// lo stesso e mostra l'ultimo briefing scaricato, con la sua data bene in vista.
// Un dato vecchio dichiarato e' utile; un dato vecchio spacciato per fresco e'
// pericoloso. E un captive portal di marina che risponde 200 con l'HTML del
// login NON deve sovrascrivere l'ultimo briefing buono: si cache-a solo JSON ok.
// SHELL si bumpa a ogni release del guscio; DATA NON si rinomina mai
// (l'activate cancella le cache con altri nomi: si perderebbe l'ultimo
// briefing buono per l'offline).
const SHELL = "nina-shell-v72";
const DATA = "nina-data-v1";
const FILES = ["./", "./index.html", "./skipper.html", "./classifica.html", "./aneddoti.html", "./mete.html", "./barca.html", "./arrivi.html", "./avionica.html", "./guida.html", "./membro.html", "./viaggio.html", "./paese.html", "./foto.html", "./manifesto.html", "./unisciti.html", "./theme.js", "./nav.js", "./ranks.js", "./manifest.json",
               "./icon-192.png", "./icon-512.png", "./icon-180.png"];
const DATAFILES = ["./data/briefing.json", "./data/weather.json", "./data/conti.json",
                   "./data/program.json", "./data/destinations.json", "./data/skipper.json", "./data/crew.json", "./data/trips.json", "./data/anecdotes.json", "./data/mete.json", "./data/proposte.json"];

const isJson = r => r.ok && (r.headers.get("content-type") || "").includes("json");

self.addEventListener("install", e => {
  e.waitUntil((async () => {
    const shell = await caches.open(SHELL);
    await shell.addAll(FILES);
    // precache dati best-effort: cosi' l'offline funziona gia' dalla prima
    // visita, e un fallimento qui non deve bloccare l'install del guscio
    const data = await caches.open(DATA);
    await Promise.allSettled(DATAFILES.map(u => data.add(u)));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", e => {
  e.waitUntil((async () => {
    const ks = await caches.keys();
    await Promise.all(ks.filter(k => k !== SHELL && k !== DATA).map(k => caches.delete(k)));
    await self.clients.claim();
    // guscio nuovo attivato: ricarica UNA volta le finestre aperte così prendono
    // subito la versione appena deployata (niente client fermi su quella vecchia).
    const wins = await self.clients.matchAll({ type: "window" });
    for (const w of wins) { try { w.navigate(w.url); } catch (err) {} }
  })());
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;

  if (url.pathname.includes("/data/")) {
    e.respondWith(
      fetch(e.request).then(r => {
        if (isJson(r)) {
          const copy = r.clone();
          caches.open(DATA).then(c => c.put(e.request, copy));
          return r;
        }
        // 404, redirect di captive portal, HTML: meglio l'ultimo JSON buono
        return caches.match(e.request).then(m => m || r);
      }).catch(() => caches.match(e.request))
    );
    return;
  }

  // PAGINE HTML (navigazioni): network-first con timeout. Online = sempre l'ultima
  // versione appena deployata (niente hard-refresh dopo un aggiornamento); offline o
  // rete lenta (>3.5s) = ultima versione buona dalla cache. In rada senza rete si apre
  // comunque, e un deploy nuovo si vede subito appena c'e' segnale.
  if (e.request.mode === "navigation") {
    e.respondWith((async () => {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 3500);
      try {
        const net = await fetch(e.request, { signal: ctrl.signal });
        clearTimeout(t);
        if (net && net.ok) {
          caches.open(SHELL).then(c => c.put(e.request, net.clone()));
          return net;
        }
        return (await caches.match(e.request)) || net;
      } catch (err) {
        clearTimeout(t);
        return (await caches.match(e.request)) || (await caches.match("./index.html")) || Response.error();
      }
    })());
    return;
  }

  // altri asset del guscio (js, icone, manifest): stale-while-revalidate
  e.respondWith(caches.match(e.request).then(cached => {
    const fresh = fetch(e.request).then(r => {
      if (r.ok) {
        const copy = r.clone();
        caches.open(SHELL).then(c => c.put(e.request, copy));
      }
      return r;
    }).catch(() => cached);
    return cached || fresh;
  }));
});
