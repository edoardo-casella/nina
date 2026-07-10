"""Foto delle destinazioni da Wikimedia Commons (geosearch per coordinate).

Gratuito, senza API key, hotlink lecito (upload.wikimedia.org). Le foto si
risolvono a publish-time e finiscono nei JSON come URL: il sito resta statico.

GET dedicato (non weather._get): Commons risponde 429 alle raffiche, quindi
qui c'e' throttle di 0.5 s tra le chiamate, retry che rispetta Retry-After e
cache di 7 giorni (le foto non cambiano come il vento). `_get` e' generico
(Wikimedia): lo riusa anche enrich_destinations.py per Wikipedia.

Una foto puo' mancare (rada remota, solo mappe nei dintorni): chi consuma
deve reggere `None`. Le foto NON devono mai bloccare il briefing.
"""
from __future__ import annotations
import hashlib, json, tempfile, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

CACHE = Path(tempfile.gettempdir()) / "sailing_wx_cache"
CACHE.mkdir(parents=True, exist_ok=True)
TTL_S = 7 * 86400
UA = "nina-sailing-agent/1.0 github.com/edoardo-casella/nina"
_MIN_INTERVAL_S = 1.0
_last_call = [0.0]
# circuito: al primo 429 che esaurisce i retry si smette di chiamare Commons
# per tutto il run (gli IP condivisi dei runner CI restano limitati a lungo);
# publish.py ripiega sulle foto dell'ultimo program.json committato
_rate_limited = [False]

COMMONS = "https://commons.wikimedia.org/w/api.php"


def _get(url: str, params: dict) -> dict:
    q = urllib.parse.urlencode(params, doseq=True)
    full = f"{url}?{q}"
    key = CACHE / (hashlib.sha1(full.encode()).hexdigest() + ".json")
    if key.exists() and time.time() - key.stat().st_mtime < TTL_S:
        return json.loads(key.read_text(encoding="utf-8"))
    if _rate_limited[0]:
        raise RuntimeError("Commons rate-limited: niente altre chiamate in questo run")
    for attempt in (1, 2):
        pause = _MIN_INTERVAL_S - (time.time() - _last_call[0])
        if pause > 0:
            time.sleep(pause)
        _last_call[0] = time.time()
        try:
            req = urllib.request.Request(full, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read())
            key.write_text(json.dumps(data), encoding="utf-8")
            return data
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            if attempt == 1:
                time.sleep(min(float(e.headers.get("Retry-After") or 3), 5))
                continue
            _rate_limited[0] = True
            raise
# titoli che quasi sicuramente non sono panorami
SKIP_WORDS = ("map", "karte", "carte", "mappa", "plan", "diagram", "logo",
              "flag", "coat", "stemma", "escudo", "chart", "locator")
# parole troppo generiche per identificare la rada nel titolo di una foto
GENERIC = {"cala", "calla", "porto", "porti", "golfo", "golfe", "baie", "baia",
           "isola", "isole", "iles", "ile", "punta", "capo", "anse", "plage",
           "spiaggia", "rada", "santa", "santo", "corsica", "corse", "sardegna"}
EXT_OK = (".jpg", ".jpeg", ".png")


def tokens_of(name: str | None) -> list[str]:
    """Parole distintive del nome (>=4 char, non generiche) per il matching
    con i titoli — condiviso tra foto (Commons) e articoli (Wikipedia)."""
    return [t for t in (name or "").lower().replace("(", " ").replace(")", " ")
            .replace("-", " ").split() if len(t) >= 4 and t not in GENERIC]


def _candidates(lat: float, lon: float, name: str | None,
                radius_m: int, width: int) -> list[dict]:
    """Foto georeferenziate entro `radius_m`, ordinate best-first: prima il
    match di nome nel titolo, poi la vicinanza (il faro sbagliato vicino non
    deve battere la rada giusta un po' piu' lontana)."""
    try:
        data = _get(COMMONS, {
            "action": "query", "format": "json", "generator": "geosearch",
            "ggscoord": f"{lat}|{lon}", "ggsradius": radius_m, "ggslimit": 20,
            "ggsnamespace": 6, "prop": "imageinfo", "iiprop": "url",
            "iiurlwidth": width,
        })
    except Exception:
        return []
    pages = (data.get("query") or {}).get("pages") or {}
    tokens = tokens_of(name)
    scored = []
    for p in pages.values():
        title = p.get("title", "").lower()
        if not title.endswith(EXT_OK) or any(w in title for w in SKIP_WORDS):
            continue
        info = (p.get("imageinfo") or [{}])[0]
        if not info.get("thumburl"):
            continue
        key = (any(t in title for t in tokens), -p.get("index", 99))
        scored.append((key, {"src": info["thumburl"], "page": info.get("descriptionurl")}))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored]


def gallery_for(lat: float, lon: float, name: str | None = None,
                n: int = 6, width: int = 800) -> list[dict]:
    """Fino a `n` foto per il punto, raggi crescenti (le rade remote non hanno
    scatti entro 1.5 km). Dedup per URL. Ogni voce: {src, page}."""
    seen, gal = set(), []
    for radius_m in (1500, 4000):
        for c in _candidates(lat, lon, name, radius_m, width):
            if c["src"] not in seen:
                seen.add(c["src"])
                gal.append(c)
        if len(gal) >= n:
            break
    return gal[:n]


def photo_for(lat: float, lon: float, name: str | None = None,
              width: int = 480) -> dict | None:
    """La singola foto migliore per il punto: {src, page} o None."""
    g = gallery_for(lat, lon, name, n=1, width=width)
    return g[0] if g else None


if __name__ == "__main__":
    import sys
    lat, lon = float(sys.argv[1]), float(sys.argv[2])
    for p in gallery_for(lat, lon, sys.argv[3] if len(sys.argv) > 3 else None):
        print(p["src"])
