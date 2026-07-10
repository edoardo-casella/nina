"""Foto delle destinazioni da Wikimedia Commons (geosearch per coordinate).

Gratuito, senza API key, hotlink lecito (upload.wikimedia.org). Le foto si
risolvono a publish-time e finiscono nei JSON come URL: il sito resta statico.

GET dedicato (non weather._get): Commons risponde 429 alle raffiche, quindi
qui c'e' throttle di 0.5 s tra le chiamate, retry che rispetta Retry-After e
cache di 7 giorni (le foto non cambiano come il vento).

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
_MIN_INTERVAL_S = 0.5
_last_call = [0.0]

COMMONS = "https://commons.wikimedia.org/w/api.php"


def _get(url: str, params: dict) -> dict:
    q = urllib.parse.urlencode(params, doseq=True)
    full = f"{url}?{q}"
    key = CACHE / (hashlib.sha1(full.encode()).hexdigest() + ".json")
    if key.exists() and time.time() - key.stat().st_mtime < TTL_S:
        return json.loads(key.read_text(encoding="utf-8"))
    for attempt in (1, 2, 3):
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
            if e.code == 429 and attempt < 3:
                time.sleep(min(float(e.headers.get("Retry-After") or 2 * attempt), 30))
                continue
            raise
# titoli che quasi sicuramente non sono panorami
SKIP_WORDS = ("map", "karte", "carte", "mappa", "plan", "diagram", "logo",
              "flag", "coat", "stemma", "escudo", "chart", "locator")
# parole troppo generiche per identificare la rada nel titolo di una foto
GENERIC = {"cala", "calla", "porto", "porti", "golfo", "golfe", "baie", "baia",
           "isola", "isole", "iles", "ile", "punta", "capo", "anse", "plage",
           "spiaggia", "rada", "santa", "santo", "corsica", "corse", "sardegna"}
EXT_OK = (".jpg", ".jpeg", ".png")


def photo_for(lat: float, lon: float, name: str | None = None,
              width: int = 480) -> dict | None:
    """Foto per il punto, provando raggi crescenti (le rade remote non hanno
    scatti entro 1.5 km). Ritorna {src, page} o None."""
    for radius_m in (1500, 4000):
        p = _photo_at(lat, lon, name, radius_m, width)
        if p:
            return p
    return None


def _photo_at(lat: float, lon: float, name: str | None,
              radius_m: int, width: int) -> dict | None:
    """La foto georeferenziata piu' vicina al punto: {src, page} o None.
    Se `name` e' dato, preferisce le foto col nome della rada nel titolo
    (il faro sbagliato vicino batte la rada giusta solo per distanza)."""
    try:
        data = _get(COMMONS, {
            "action": "query", "format": "json", "generator": "geosearch",
            "ggscoord": f"{lat}|{lon}", "ggsradius": radius_m, "ggslimit": 10,
            "ggsnamespace": 6, "prop": "imageinfo", "iiprop": "url",
            "iiurlwidth": width,
        })
    except Exception:
        return None
    pages = (data.get("query") or {}).get("pages") or {}
    tokens = [t for t in (name or "").lower().replace("(", " ").replace(")", " ")
              .replace("-", " ").split() if len(t) >= 4 and t not in GENERIC]
    best = None      # (match_nome, -index): vince il match, poi la vicinanza
    for p in pages.values():
        title = p.get("title", "").lower()
        if not title.endswith(EXT_OK) or any(w in title for w in SKIP_WORDS):
            continue
        info = (p.get("imageinfo") or [{}])[0]
        if not info.get("thumburl"):
            continue
        key = (any(t in title for t in tokens), -p.get("index", 99))
        if best is None or key > best[0]:
            best = (key, {"src": info["thumburl"],
                          "page": info.get("descriptionurl")})
    return best[1] if best else None


if __name__ == "__main__":
    import sys
    lat, lon = float(sys.argv[1]), float(sys.argv[2])
    print(photo_for(lat, lon))
