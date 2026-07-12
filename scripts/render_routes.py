#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_routes.py — Genera immagini "nautico chiaro" delle rotte dei viaggi.

- Fonte: data/Viaggi in barca (2011-2024).kml (un <Folder> per viaggio).
- Rotte FLUIDE: spline centripetal Catmull-Rom (passa per i punti reali).
- SOLO MARE: si disegna la rotta, poi la terraferma opaca SOPRA (Natural Earth 10m)
  -> gli attraversamenti di terra spariscono sotto la costa.
- Output in staging: data/route-images/  (NON tocca il sito).
    _global.png            mappa globale (2 pannelli: Mediterraneo + Caraibi)
    <slug>.png             una rotta per viaggio
    routes.json            manifest slug -> metadati

Dipendenze: solo Pillow + numpy (gia' presenti). Anti-alias via supersampling.

Uso:
    python scripts/render_routes.py            # PILOTA: globale + 3 campione
    python scripts/render_routes.py --all      # globale + tutti i viaggi
    python scripts/render_routes.py --only "Cyclades 2024"
"""
import argparse
import json
import math
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# riuso utility dal merge
sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_percorsi import read_kml_text, kml_color  # noqa: E402

KML_NS = "http://www.opengis.net/kml/2.2"
_Q = lambda t: f"{{{KML_NS}}}{t}"

# --- percorsi ---------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
SRC_KML = ROOT / "data" / "Viaggi in barca (2011-2024).kml"
GEO_DIR = ROOT / "data" / "geo"
OUT_DIR = ROOT / "data" / "route-images"
LAND_FILES = ["ne_10m_land.geojson", "ne_10m_minor_islands.geojson"]
BORDER_FILE = "ne_10m_admin_0_boundary_lines_land.geojson"
OSM_DIR = GEO_DIR / "osm"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# colori etichette geografiche
LABEL_INK = (35, 45, 55)
ISLAND_INK = (74, 62, 40)
COVE_INK = (22, 92, 140)
TOWN_DOT = (60, 70, 80)
COUNTRY_INK = (196, 172, 138)   # nome stato "in filigrana" (poco più scuro della terra)
BORDER_COL = (150, 96, 120)     # confine di stato tratteggiato

# soglie di vicinanza alla rotta (km) e tetti per categoria
NEAR = {"town": 6.0, "village": 3.5, "island": 25.0, "islet": 4.5, "cove": 3.5, "poi": 4.0}
CAP = {"poi": 16, "town": 18, "island": 16, "cove": 16}

# gazetteer curato: nomi delle isole maggiori (name, lat, lon) — etichettate se il
# centro cade dentro la vista (le isole enormi mostrate a meta' restano senza scritta).
MAJOR_ISLANDS = [
    # Baleari
    ("Mallorca", 39.60, 3.00), ("Menorca", 39.95, 4.10), ("Ibiza", 38.98, 1.43),
    ("Formentera", 38.70, 1.46), ("Cabrera", 39.15, 2.94), ("Dragonera", 39.58, 2.33),
    # Tirreno / Sardegna / Corsica
    ("Corsica", 42.15, 9.08), ("Sardegna", 40.10, 9.05), ("La Maddalena", 41.22, 9.41),
    ("Caprera", 41.20, 9.47), ("Asinara", 41.05, 8.28), ("San Pietro", 39.13, 8.28),
    ("Sant'Antioco", 39.06, 8.44), ("Tavolara", 40.90, 9.72),
    # Sicilia / Egadi
    ("Sicilia", 37.58, 14.15), ("Favignana", 37.93, 12.33), ("Levanzo", 38.00, 12.34),
    ("Marettimo", 37.97, 12.07), ("Ustica", 38.71, 13.19), ("Pantelleria", 36.79, 11.99),
    # Adriatico (Croazia)
    ("Hvar", 43.13, 16.75), ("Brač", 43.32, 16.65), ("Vis", 43.04, 16.18),
    ("Biševo", 42.98, 16.02), ("Korčula", 42.95, 17.05), ("Lastovo", 42.76, 16.90),
    ("Mljet", 42.75, 17.55), ("Šolta", 43.38, 16.30), ("Šćedro", 43.09, 16.72),
    ("Pelješac", 42.95, 17.35), ("Dugi Otok", 44.02, 15.05), ("Kornat", 43.80, 15.30),
    ("Žirje", 43.65, 15.67), ("Pašman", 43.93, 15.37), ("Ugljan", 44.08, 15.17),
    ("Molat", 44.22, 14.87), ("Ist", 44.28, 14.78),
    # Ionio
    ("Corfù", 39.62, 19.85), ("Paxos", 39.20, 20.18), ("Antipaxos", 39.15, 20.23),
    ("Lefkada", 38.72, 20.65), ("Meganisi", 38.66, 20.77), ("Kefalonia", 38.25, 20.55),
    ("Itaca", 38.40, 20.72), ("Zante", 37.79, 20.75),
    # Cicladi
    ("Kea", 37.62, 24.33), ("Kythnos", 37.40, 24.43), ("Serifos", 37.15, 24.50),
    ("Sifnos", 36.98, 24.68), ("Milos", 36.70, 24.44), ("Kimolos", 36.80, 24.57),
    ("Polyaigos", 36.76, 24.65), ("Antiparos", 37.03, 25.02), ("Paros", 37.08, 25.15),
    ("Naxos", 37.05, 25.53), ("Mykonos", 37.45, 25.37), ("Syros", 37.44, 24.92),
    ("Tinos", 37.60, 25.16), ("Andros", 37.84, 24.87), ("Ios", 36.72, 25.28),
    ("Folegandros", 36.62, 24.92), ("Sikinos", 36.68, 25.10), ("Amorgos", 36.83, 25.90),
    ("Gyaros", 37.62, 24.72),
    # Dodecaneso
    ("Rodi", 36.20, 27.95), ("Kos", 36.85, 27.20), ("Kalymnos", 36.98, 26.98),
    ("Leros", 37.15, 26.85), ("Patmos", 37.31, 26.55), ("Lipsi", 37.30, 26.77),
    ("Symi", 36.60, 27.84), ("Astypalea", 36.55, 26.35), ("Nisyros", 36.58, 27.16),
    ("Tilos", 36.42, 27.38),
    # Sporadi
    ("Skiathos", 39.16, 23.49), ("Skopelos", 39.12, 23.72), ("Alonnisos", 39.15, 23.87),
    ("Skyros", 38.88, 24.57),
    # Saronico
    ("Egina", 37.74, 23.47), ("Poros", 37.50, 23.46), ("Hydra", 37.34, 23.47),
    ("Spetses", 37.26, 23.16), ("Salamina", 37.96, 23.49),
    # Caraibi (Grenadine + Cuba)
    ("Grenada", 12.12, -61.68), ("Carriacou", 12.48, -61.45), ("Union Island", 12.60, -61.44),
    ("Mayreau", 12.64, -61.39), ("Canouan", 12.70, -61.33), ("Tobago Cays", 12.63, -61.35),
    ("Mustique", 12.88, -61.19), ("Bequia", 13.01, -61.24), ("Saint Vincent", 13.25, -61.20),
    ("Cayo Largo", 21.62, -81.57), ("Isla de la Juventud", 21.70, -82.82),
]

# nomi degli stati (name, [ancore lat,lon]) — etichettato all'ancora in vista.
COUNTRIES = [
    ("Italia", [(42.4, 12.6), (41.15, 9.45), (40.9, 9.15), (40.3, 9.35), (37.6, 14.2),
                (45.2, 9.3), (40.5, 17.4), (43.2, 11.6)]),
    ("Francia", [(43.6, 6.2), (41.95, 9.25), (44.8, 4.6)]),
    ("Spagna", [(39.75, 3.15), (39.5, -3.5), (41.5, 1.6), (38.9, -1.5)]),
    ("Croazia", [(45.1, 15.6), (43.55, 16.2), (43.05, 17.35), (44.6, 15.2)]),
    ("Slovenia", [(45.95, 14.8)]),
    ("Montenegro", [(42.6, 19.15)]),
    ("Bosnia", [(43.9, 17.7)]),
    ("Albania", [(41.0, 20.0), (40.3, 19.8)]),
    ("Grecia", [(39.0, 22.0), (36.85, 24.9), (36.4, 27.9), (38.9, 20.75), (40.2, 23.4)]),
    ("Turchia", [(37.1, 27.7), (36.85, 28.75), (38.4, 27.2), (39.6, 32.0)]),
    ("Tunisia", [(35.6, 10.3), (36.9, 10.2)]),
    ("Malta", [(35.9, 14.45)]),
    ("Cuba", [(21.95, -79.4), (21.75, -80.7), (22.0, -78.3), (20.4, -76.8)]),
    ("Grenada", [(12.11, -61.70)]),
    ("Saint Vincent", [(13.2, -61.2), (12.6, -61.47)]),
]

# isole grandi da etichettare anche sulla mappa globale (scala d'insieme)
GLOBAL_ISLANDS = [
    ("Sicilia", 37.58, 14.15), ("Sardegna", 40.10, 9.05), ("Corsica", 42.15, 9.08),
    ("Mallorca", 39.60, 3.00), ("Menorca", 39.95, 4.10), ("Ibiza", 38.98, 1.43),
    ("Creta", 35.24, 24.80), ("Eubea", 38.55, 23.80), ("Rodi", 36.15, 27.95),
    ("Corfù", 39.62, 19.85), ("Cipro", 35.10, 33.20),
]

# traslitterazione greco -> latino (i pochi nomi senza name:en/it)
_GREEK = {"Α": "A", "Β": "V", "Γ": "G", "Δ": "D", "Ε": "E", "Ζ": "Z", "Η": "I",
          "Θ": "Th", "Ι": "I", "Κ": "K", "Λ": "L", "Μ": "M", "Ν": "N", "Ξ": "X",
          "Ο": "O", "Π": "P", "Ρ": "R", "Σ": "S", "Τ": "T", "Υ": "Y", "Φ": "F",
          "Χ": "Ch", "Ψ": "Ps", "Ω": "O",
          "α": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "i",
          "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x",
          "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "y",
          "φ": "f", "χ": "ch", "ψ": "ps", "ω": "o"}


def _translit(s):
    if not any("Ͱ" <= c <= "Ͽ" or "ἀ" <= c <= "῿" for c in s):
        return s
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))
    return "".join(_GREEK.get(c, c) for c in s)

PILOT_TRIPS = ["Croazia '18", "Cyclades 2024", "Caribe '17"]

# --- palette "nautico chiaro" ----------------------------------------------
SEA = (191, 217, 236)      # #BFD9EC
LAND = (234, 224, 200)     # #EAE0C8
COAST = (176, 158, 112)    # #B09E70
CASING = (255, 255, 255)
PARCHMENT = (244, 241, 232) # #F4F1E8
INK = (44, 54, 64)
START_COL = (30, 150, 85)  # verde
END_COL = (200, 60, 50)    # rosso
TRIP_ROUTE_COL = (214, 58, 47)  # rosso vermiglio uniforme per le schede singole

# --- geometria / proiezione -------------------------------------------------

def slugify(s: str) -> str:
    s = s.replace("’", "'").replace("`", "'")
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s


def coords_to_np(text: str) -> np.ndarray:
    pts = []
    for tok in text.split():
        parts = tok.split(",")
        if len(parts) >= 2:
            pts.append((float(parts[0]), float(parts[1])))  # lon, lat
    return np.array(pts, float)


def load_trips(kml_path: Path):
    """Ritorna (trips, trackless). trip = dict(name, slug, lonlat, region)."""
    root = ET.fromstring(read_kml_text(kml_path))
    parent = {c: p for p in root.iter() for c in p}

    def nearest_folder_name(node):
        while node is not None:
            if node.tag == _Q("Folder"):
                nm = node.find(_Q("name"))
                if nm is not None and nm.text:
                    return nm.text.strip()
            node = parent.get(node)
        return None

    trips = []
    seen_folders = set()
    for pm in root.iter(_Q("Placemark")):
        ls = pm.find(".//" + _Q("LineString"))
        if ls is None:
            continue
        coords_el = ls.find(_Q("coordinates"))
        if coords_el is None or not coords_el.text:
            continue
        lonlat = coords_to_np(coords_el.text)
        if len(lonlat) < 2:
            continue
        name = nearest_folder_name(pm)
        if not name:
            nm = pm.find(_Q("name"))
            name = (nm.text.strip() if nm is not None and nm.text else "Senza nome")
        name = name.replace("’", "'")
        seen_folders.add(name)
        trips.append({
            "name": name,
            "slug": slugify(name),
            "lonlat": lonlat,
            "region": "caribbean" if lonlat[:, 0].mean() < -20 else "med",
        })

    # cartelle senza traccia (nessuna LineString discendente)
    trackless = []
    for folder in root.iter(_Q("Folder")):
        nm = folder.find(_Q("name"))
        nmtxt = nm.text.strip().replace("’", "'") if nm is not None and nm.text else None
        if not nmtxt:
            continue
        has_line = next(folder.iter(_Q("LineString")), None) is not None
        if not has_line and nmtxt not in seen_folders:
            trackless.append(nmtxt)

    trips.sort(key=lambda t: t["name"].lower())
    return trips, trackless


# --- smoothing --------------------------------------------------------------

def _project(lonlat, lat0):
    cl = math.cos(math.radians(lat0))
    xy = lonlat.copy()
    xy[:, 0] = lonlat[:, 0] * cl
    return xy, cl


def catmull_rom(P, samples=24, alpha=0.5):
    """Spline interpolante centripetal (passa per i punti). P: (N,2) proiettato."""
    P = np.asarray(P, float)
    if len(P) < 4:
        return P
    P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        def tj(ti, a, b):
            d = np.linalg.norm(b - a) ** alpha
            return ti + (d if d > 1e-9 else 1e-9)
        t0 = 0.0
        t1 = tj(t0, p0, p1)
        t2 = tj(t1, p1, p2)
        t3 = tj(t2, p2, p3)
        t = np.linspace(t1, t2, samples, endpoint=False)[:, None]
        A1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
        A2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
        A3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
        B1 = (t2 - t) / (t2 - t0) * A1 + (t - t0) / (t2 - t0) * A2
        B2 = (t3 - t) / (t3 - t1) * A2 + (t - t1) / (t3 - t1) * A3
        out.append((t2 - t) / (t2 - t1) * B1 + (t - t1) / (t2 - t1) * B2)
    return np.vstack(out + [P[-2][None]])


def chaikin(P, iters=3):
    P = np.asarray(P, float)
    for _ in range(iters):
        if len(P) < 3:
            break
        new = [P[0]]
        for i in range(len(P) - 1):
            a, b = P[i], P[i + 1]
            new.append(0.75 * a + 0.25 * b)
            new.append(0.25 * a + 0.75 * b)
        new.append(P[-1])
        P = np.array(new)
    return P


def smooth_track(lonlat):
    lat0 = float(lonlat[:, 1].mean())
    xy, cl = _project(lonlat, lat0)
    dense = catmull_rom(xy) if len(xy) >= 4 else chaikin(xy, 2)
    dense = dense.copy()
    dense[:, 0] = dense[:, 0] / cl  # unproject
    return dense


# --- Natural Earth ----------------------------------------------------------

def _rings_from_geometry(geom):
    """Yield (exterior np(N,2), [holes]) per Polygon/MultiPolygon."""
    t = geom.get("type")
    coords = geom.get("coordinates")
    if t == "Polygon":
        polys = [coords]
    elif t == "MultiPolygon":
        polys = coords
    else:
        return
    for poly in polys:
        if not poly:
            continue
        ext = np.array(poly[0], float)[:, :2]
        holes = [np.array(h, float)[:, :2] for h in poly[1:]]
        yield ext, holes


def load_land():
    """Lista di (ext, holes, bbox) da tutti i geojson."""
    polys = []
    for fn in LAND_FILES:
        p = GEO_DIR / fn
        if not p.exists():
            sys.exit(f"ERRORE: manca {p}. Scaricare i Natural Earth 10m in data/geo/.")
        gj = json.loads(p.read_text(encoding="utf-8"))
        for feat in gj.get("features", []):
            geom = feat.get("geometry") or {}
            for ext, holes in _rings_from_geometry(geom):
                bbox = (ext[:, 0].min(), ext[:, 1].min(), ext[:, 0].max(), ext[:, 1].max())
                polys.append((ext, holes, bbox))
    return polys


def load_borders():
    """Linee di confine di stato (Natural Earth). Lista di (arr Nx2, bbox)."""
    p = GEO_DIR / BORDER_FILE
    if not p.exists():
        return []
    gj = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for feat in gj.get("features", []):
        geom = feat.get("geometry") or {}
        t = geom.get("type")
        coords = geom.get("coordinates")
        segs = [coords] if t == "LineString" else (coords if t == "MultiLineString" else [])
        for seg in segs:
            arr = np.array(seg, float)[:, :2]
            if len(arr) >= 2:
                bbox = (arr[:, 0].min(), arr[:, 1].min(), arr[:, 0].max(), arr[:, 1].max())
                out.append((arr, bbox))
    return out


def _draw_dashed(draw, pts, color, width, dash=15, gap=11):
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        seg = b - a
        L = math.hypot(seg[0], seg[1])
        if L < 1e-6:
            continue
        u = seg / L
        pos = 0.0
        while pos < L:
            s = a + u * pos
            e = a + u * min(pos + dash, L)
            draw.line([(s[0], s[1]), (e[0], e[1])], fill=color, width=width)
            pos += dash + gap


# --- OpenStreetMap: nomi + punti cospicui -----------------------------------

def _overpass_run(body, cap, retries=5):
    q = f"[out:json][timeout:120];({body});out center tags {cap};"
    data = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for attempt in range(retries):
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
        try:
            req = urllib.request.Request(url, data=data,
                                         headers={"User-Agent": "sailing-route-map/1.0"})
            return json.loads(urllib.request.urlopen(req, timeout=180).read().decode("utf-8"))
        except Exception as e:  # 429/503/504/timeout: attende ed eventualmente cambia mirror
            last = e
            time.sleep(4 * (attempt + 1))
    raise last


def _overpass(view):
    lo0, lo1, la0, la1 = view["lo0"], view["lo1"], view["la0"], view["la1"]
    bb = f"{la0},{lo0},{la1},{lo1}"  # south,west,north,east
    # "scheletro" (isole/cale/POI/citta-paesi): pochi elementi, mai saturato dal tetto
    skeleton = f"""
  node["place"~"island|islet"]["name"]({bb});
  way["place"~"island|islet"]["name"]({bb});
  rel["place"~"island|islet"]["name"]({bb});
  node["place"~"city|town"]["name"]({bb});
  node["natural"="bay"]["name"]({bb});
  way["natural"="bay"]["name"]({bb});
  node["natural"~"volcano|peak"]["name"]({bb});
  node["historic"~"castle|fort|ruins|archaeological_site|monument"]["name"]({bb});
  way["historic"~"castle|fort|ruins|archaeological_site"]["name"]({bb});
  node["man_made"="lighthouse"]["name"]({bb});
  node["natural"="beach"]["name"]({bb});
  way["natural"="beach"]["name"]({bb});"""
    villages = f'node["place"="village"]["name"]({bb});'
    r1 = _overpass_run(skeleton, 1500)
    time.sleep(1.5)
    r2 = _overpass_run(villages, 500)
    return {"elements": r1.get("elements", []) + r2.get("elements", [])}


def get_osm_raw(view, slug):
    OSM_DIR.mkdir(parents=True, exist_ok=True)
    cache = OSM_DIR / f"{slug}-v2.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    try:
        raw = _overpass(view)
    except Exception as e:
        print(f"    ! OSM non raggiungibile per {slug}: {e}")
        return {"elements": []}
    cache.write_text(json.dumps(raw), encoding="utf-8")
    time.sleep(1.0)  # cortesia verso Overpass tra un viaggio e l'altro
    return raw


def _disp_name(t):
    for k in ("name:it", "name:en", "int_name", "name"):
        if t.get(k):
            return _translit(t[k])
    return None


def _classify(t):
    """(kind, prio, emoji|None). kind in poi/town/island/cove."""
    h, mm, nat, pl = t.get("historic"), t.get("man_made"), t.get("natural"), t.get("place")
    if pl == "island":
        return ("island", 10, None)   # nome isola = priorità massima
    if h in ("castle", "fort"):
        return ("poi", 9, "🏰")
    if pl == "city":
        return ("town", 8, None)
    if nat == "volcano":
        return ("poi", 8, "🌋")
    if h in ("archaeological_site", "ruins"):
        return ("poi", 7, "🏛️")
    if mm == "lighthouse":
        return ("poi", 7, "🗼")
    if pl == "town":
        return ("town", 7, None)
    if nat == "bay":
        return ("cove", 6, None)
    if h == "monument":
        return ("poi", 6, "🗿")
    if nat == "peak":
        return ("poi", 6, "⛰️")
    if pl == "village":
        return ("town", 6, None)   # in Egeo il nome dell'isola sta spesso sul paese
    if nat == "beach":
        return ("poi", 4, "🏖️")
    if pl == "islet":
        return ("island", 3, None)  # isolotti minori: solo se molto vicini
    return (None, 0, None)


def parse_features(raw):
    out = []
    for e in raw.get("elements", []):
        t = e.get("tags", {})
        name = _disp_name(t)
        if not name:
            continue
        kind, prio, emoji = _classify(t)
        if kind is None:
            continue
        if "lat" in e:
            lat, lon = e["lat"], e["lon"]
        elif "center" in e:
            lat, lon = e["center"]["lat"], e["center"]["lon"]
        else:
            continue
        out.append({"lon": lon, "lat": lat, "name": name, "kind": kind,
                    "prio": prio, "emoji": emoji})
    return out


def curate(feats, dense):
    """Tiene solo le feature vicine alla rotta, con tetto per categoria."""
    rlon, rlat = dense[:, 0], dense[:, 1]
    kept = []
    for f in feats:
        cl = math.cos(math.radians(f["lat"]))
        dx = (rlon - f["lon"]) * cl * 111.0
        dy = (rlat - f["lat"]) * 111.0
        d = float(np.sqrt(dx * dx + dy * dy).min())
        if f["kind"] == "island":
            thr = NEAR["island"] if f["prio"] >= 6 else NEAR["islet"]
        elif f["kind"] == "town":
            thr = NEAR["town"] if f["prio"] >= 7 else NEAR["village"]
        else:
            thr = NEAR.get(f["kind"], 4.0)
        if d <= thr:
            f["dist"] = d
            kept.append(f)
    out = []
    for kind in ("poi", "town", "island", "cove"):
        grp = sorted((f for f in kept if f["kind"] == kind),
                     key=lambda f: (-f["prio"], f["dist"]))
        out += grp[:CAP[kind]]
    return out


def big_islands(view, dense):
    """Nomi isole maggiori (gazetteer). Anche isole enormi mostrate a meta' (centro
    fino al 20% fuori vista) vengono etichettate, con l'etichetta agganciata al bordo."""
    rlon, rlat = dense[:, 0], dense[:, 1]
    ex = (view["lo1"] - view["lo0"]) * 0.20
    ey = (view["la1"] - view["la0"]) * 0.20
    out = []
    for name, lat, lon in MAJOR_ISLANDS:
        if not (view["lo0"] - ex <= lon <= view["lo1"] + ex
                and view["la0"] - ey <= lat <= view["la1"] + ey):
            continue
        cl = math.cos(math.radians(lat))
        dx = (rlon - lon) * cl * 111.0
        dy = (rlat - lat) * 111.0
        d = float(np.sqrt(dx * dx + dy * dy).min())
        out.append({"lon": lon, "lat": lat, "name": name.upper(),
                    "kind": "bigisland", "prio": 11, "emoji": None, "dist": d})
    return out


def _emoji_font(size):
    try:
        return ImageFont.truetype("seguiemj.ttf", size)
    except Exception:
        return _font(size)


def annotate(img, view, dense, feats, W, H, borders=None):
    """Disegna stati/confini, isole, cale, paesi e punti cospicui sull'immagine 1x."""
    d = ImageDraw.Draw(img)
    proj1 = make_proj(view, W, H)

    # confini di stato (tratteggiati), solo i segmenti in vista
    if borders:
        for arr, bbox in borders:
            if (bbox[2] < view["lo0"] or bbox[0] > view["lo1"]
                    or bbox[3] < view["la0"] or bbox[1] > view["la1"]):
                continue
            _draw_dashed(d, proj1(arr), BORDER_COL, 2)

    # nomi degli stati "in filigrana" (sotto tutte le altre etichette)
    cfont = _font(40, bold=True)
    for name, anchors in COUNTRIES:
        for lat, lon in anchors:
            if view["lo0"] <= lon <= view["lo1"] and view["la0"] <= lat <= view["la1"]:
                p = proj1(np.array([[lon, lat]]))[0]
                txt = name.upper() if " " in name else " ".join(name.upper())
                d.text((float(p[0]), float(p[1])), txt, font=cfont, fill=COUNTRY_INK, anchor="mm")
                break

    feats = big_islands(view, dense) + curate(feats, dense)
    if not feats:
        return 0
    f_town = _font(17, bold=True)
    f_big = _font(30, bold=True, italic=True)
    f_isl = _font(19, italic=True)
    f_cove = _font(15, italic=True)
    f_poi = _font(16, bold=True)
    efont = _emoji_font(30)
    ICON = 30

    for f in feats:
        p = proj1(np.array([[f["lon"], f["lat"]]]))[0]
        f["px"] = (float(p[0]), float(p[1]))

    placed = []
    ladder = [(0, -14), (16, 0), (-16, 0), (0, 16), (22, -12), (-22, -12), (22, 12),
              (-22, 12), (0, -30), (0, 30), (38, 0), (-38, 0)]
    drawn = 0
    for f in sorted(feats, key=lambda f: (-f["prio"], f["dist"])):
        x, y = f["px"]
        if x < -20 or x > W + 20 or y < -20 or y > H + 20:
            continue
        kind = f["kind"]
        irect = None
        if kind == "poi":
            irect = (x - ICON / 2, y - ICON / 2, x + ICON / 2, y + ICON / 2)
        elif kind == "town":
            irect = (x - 6, y - 6, x + 6, y + 6)
        if irect is not None and any(_rects_overlap(irect, p) for p in placed):
            continue

        if kind == "poi":
            font, fill = f_poi, LABEL_INK
        elif kind == "town":
            font, fill = f_town, LABEL_INK
        elif kind == "bigisland":
            font, fill = f_big, (120, 105, 80)
        elif kind == "island":
            font, fill = f_isl, ISLAND_INK
        else:
            font, fill = f_cove, COVE_INK
        text = f["name"]
        bb = font.getbbox(text)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        by = y - (ICON * 0.6 if kind == "poi" else (9 if kind == "town" else 0))
        cands = ([(0, 0)] + ladder) if kind in ("island", "cove", "bigisland") else ladder
        chosen = None
        for dx, dy in cands:
            cx = min(max(x + dx, tw / 2 + 3), W - tw / 2 - 3)
            cy = min(max(by + dy, th / 2 + 3), H - th / 2 - 3)
            rect = (cx - tw / 2 - 2, cy - th / 2 - 2, cx + tw / 2 + 2, cy + th / 2 + 2)
            if any(_rects_overlap(rect, p) for p in placed):
                continue
            if irect is not None and _rects_overlap(rect, irect):
                continue
            chosen = (cx, cy, rect)
            break

        # disegna marker/icona (anche se l'etichetta non entra, per i POI/paesi)
        if kind == "poi":
            d.text((x, y), f["emoji"], font=efont, embedded_color=True, anchor="mm")
            placed.append(irect)
        elif kind == "town":
            d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=TOWN_DOT, outline=(255, 255, 255))
            placed.append(irect)
        if chosen is None:
            continue
        cx, cy, rect = chosen
        _text_halo(d, (cx, cy), text, font, fill=fill, halo=(255, 255, 255), r=2)
        placed.append(rect)
        drawn += 1
    return drawn


# --- vista / pixel ----------------------------------------------------------

def compute_view(lons, lats, out_w, out_h, pad=0.10, min_span=0.45):
    lo0, lo1 = float(lons.min()), float(lons.max())
    la0, la1 = float(lats.min()), float(lats.max())
    latmid = (la0 + la1) / 2
    cl = math.cos(math.radians(latmid))
    dlo, dla = (lo1 - lo0), (la1 - la0)
    lo0 -= dlo * pad; lo1 += dlo * pad
    la0 -= dla * pad; la1 += dla * pad
    # span minimo
    if (lo1 - lo0) < min_span / cl:
        c = (lo0 + lo1) / 2; half = min_span / cl / 2; lo0, lo1 = c - half, c + half
    if (la1 - la0) < min_span:
        c = (la0 + la1) / 2; half = min_span / 2; la0, la1 = c - half, c + half
    # adatta all'aspect del canvas
    target = out_w / out_h
    geoW = (lo1 - lo0) * cl; geoH = (la1 - la0)
    if geoW / geoH < target:
        newW = target * geoH
        extra = (newW - geoW) / cl
        lo0 -= extra / 2; lo1 += extra / 2
    else:
        newH = geoW / target
        extra = newH - geoH
        la0 -= extra / 2; la1 += extra / 2
    return {"lo0": lo0, "lo1": lo1, "la0": la0, "la1": la1}


def make_proj(view, W, H):
    lo0, lo1, la0, la1 = view["lo0"], view["lo1"], view["la0"], view["la1"]
    def proj(lonlat):
        x = (lonlat[:, 0] - lo0) / (lo1 - lo0) * W
        y = (la1 - lonlat[:, 1]) / (la1 - la0) * H
        return np.column_stack([x, y])
    return proj


def draw_land(draw, polys, view, W, H, coast_w=1, mask=False):
    lo0, lo1, la0, la1 = view["lo0"], view["lo1"], view["la0"], view["la1"]
    proj = make_proj(view, W, H)
    land_col = 255 if mask else LAND
    sea_col = 0 if mask else SEA
    coast_col = None if mask else COAST
    for ext, holes, bbox in polys:
        if bbox[2] < lo0 or bbox[0] > lo1 or bbox[3] < la0 or bbox[1] > la1:
            continue
        pe = proj(ext)
        if len(pe) < 3:
            continue
        seq = [tuple(p) for p in pe]
        draw.polygon(seq, fill=land_col, outline=(coast_col if coast_w else None))
        for h in holes:
            ph = proj(h)
            if len(ph) >= 3:
                draw.polygon([tuple(p) for p in ph], fill=sea_col)


def _font(size, bold=False, italic=False):
    if bold and italic:
        cands = ["arialbi.ttf", "DejaVuSans-BoldOblique.ttf"]
    elif italic:
        cands = ["ariali.ttf", "DejaVuSans-Oblique.ttf"]
    elif bold:
        cands = ["arialbd.ttf", "Arialbd.ttf", "DejaVuSans-Bold.ttf", "seguisb.ttf"]
    else:
        cands = ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "segoeui.ttf"]
    for c in cands:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _text_halo(draw, xy, text, font, fill=(255, 255, 255), halo=INK, r=2, anchor="mm"):
    x, y = xy
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=halo, anchor=anchor)
    draw.text((x, y), text, font=font, fill=fill, anchor=anchor)


# --- render per-trip --------------------------------------------------------

def render_trip(trip, polys, out_w=1600, out_h=1120, S=3, with_labels=True, borders=None):
    W, H = out_w * S, out_h * S
    lonlat = trip["lonlat"]
    dense = smooth_track(lonlat)
    view = compute_view(lonlat[:, 0], lonlat[:, 1], out_w, out_h)
    proj = make_proj(view, W, H)
    route_px = proj(dense)
    col = TRIP_ROUTE_COL  # rosso nautico uniforme su tutte le schede

    img = Image.new("RGB", (W, H), SEA)
    d = ImageDraw.Draw(img)
    seq = [tuple(p) for p in route_px]
    casing_w = max(3, int(9 * S))
    route_w = max(2, int(5 * S))
    d.line(seq, fill=CASING, width=casing_w, joint="curve")
    d.line(seq, fill=col, width=route_w, joint="curve")
    # cap tondi
    for p in (route_px[0], route_px[-1]):
        r = route_w / 2
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=col)

    # QC "solo mare" PRIMA dell'overlay
    mask = Image.new("1", (W, H), 0)
    md = ImageDraw.Draw(mask)
    draw_land(md, polys, view, W, H, coast_w=0, mask=True)
    marr = np.asarray(mask)
    xs = np.clip(route_px[:, 0].astype(int), 0, W - 1)
    ys = np.clip(route_px[:, 1].astype(int), 0, H - 1)
    on_land = float(marr[ys, xs].mean()) * 100.0

    # terra OPACA sopra la rotta -> solo mare
    draw_land(d, polys, view, W, H, coast_w=1)

    # marker start/end sopra la terra
    for p, c in ((route_px[0], START_COL), (route_px[-1], END_COL)):
        r = max(6, int(11 * S))
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=c, outline=(255, 255, 255), width=max(2, S))

    img = img.resize((out_w, out_h), Image.LANCZOS)

    # annotazioni geografiche (OSM): isole, cale, paesi, punti cospicui
    n_labels = 0
    if with_labels:
        feats = parse_features(get_osm_raw(view, trip["slug"]))
        n_labels = annotate(img, view, dense, feats, out_w, out_h, borders=borders)

    out = OUT_DIR / f"{trip['slug']}.png"
    img.save(out, "PNG", optimize=True)
    return {"slug": trip["slug"], "file": out.name, "trip_name": trip["name"],
            "region": trip["region"], "w": out_w, "h": out_h,
            "bbox": [round(view["lo0"], 4), round(view["la0"], 4),
                     round(view["lo1"], 4), round(view["la1"], 4)],
            "on_land_pct": round(on_land, 1),
            "points": int(len(lonlat)), "labels": n_labels}


# --- render globale ---------------------------------------------------------

def _rects_overlap(a, b):
    return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])


def _place_labels(draw, panel_w, panel_h, items, font):
    """items: [((ax,ay), text)]. Posizionamento greedy anti-collisione + leader line."""
    placed = []
    ladder = [(0, -16), (0, 16), (0, -34), (0, 34), (46, -16), (-46, -16), (46, 16),
              (-46, 16), (0, -54), (0, 54), (84, 0), (-84, 0), (64, -40), (-64, -40),
              (64, 40), (-64, 40)]
    for (ax, ay), text in sorted(items, key=lambda it: it[0][1]):
        bb = font.getbbox(text)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        chosen = None
        for dx, dy in ladder:
            cx = min(max(ax + dx, tw / 2 + 4), panel_w - tw / 2 - 4)
            cy = min(max(ay + dy, th / 2 + 4), panel_h - th / 2 - 4)
            rect = (cx - tw / 2 - 3, cy - th / 2 - 3, cx + tw / 2 + 3, cy + th / 2 + 3)
            if not any(_rects_overlap(rect, p) for p in placed):
                chosen = (cx, cy, rect)
                break
        if chosen is None:
            cx, cy = ax + ladder[0][0], ay + ladder[0][1]
            rect = (cx - tw / 2 - 3, cy - th / 2 - 3, cx + tw / 2 + 3, cy + th / 2 + 3)
            chosen = (cx, cy, rect)
        cx, cy, rect = chosen
        if abs(cx - ax) > 22 or abs(cy - ay) > 22:
            draw.line([(ax, ay), (cx, cy)], fill=INK, width=1)
        placed.append(rect)
        _text_halo(draw, (cx, cy), text, font, fill=INK, halo=(255, 255, 255), r=2)


def _region_panel(trips, polys, panel_w, S=2, pad=0.12, min_span=0.5, borders=None):
    alllon = np.concatenate([t["lonlat"][:, 0] for t in trips])
    alllat = np.concatenate([t["lonlat"][:, 1] for t in trips])
    latmid = (alllat.min() + alllat.max()) / 2
    cl = math.cos(math.radians(latmid))
    geoW = (alllon.max() - alllon.min()) * cl * (1 + 2 * pad)
    geoH = (alllat.max() - alllat.min()) * (1 + 2 * pad)
    panel_h = int(round(panel_w * geoH / max(geoW, 1e-9)))
    panel_h = max(int(panel_w * 0.42), min(panel_h, int(panel_w * 1.15)))
    W, H = panel_w * S, panel_h * S
    view = compute_view(alllon, alllat, panel_w, panel_h, pad=pad, min_span=min_span)
    projS = make_proj(view, W, H)
    img = Image.new("RGB", (W, H), SEA)
    d = ImageDraw.Draw(img)
    for t in trips:
        rp = projS(smooth_track(t["lonlat"]))
        col = tuple(int(t["_hex"][i:i + 2], 16) for i in (1, 3, 5))
        seq = [tuple(p) for p in rp]
        d.line(seq, fill=CASING, width=max(2, int(4 * S)), joint="curve")
        d.line(seq, fill=col, width=max(1, int(2.4 * S)), joint="curve")
    draw_land(d, polys, view, W, H, coast_w=1)
    img = img.resize((panel_w, panel_h), Image.LANCZOS)
    d1 = ImageDraw.Draw(img)
    proj1 = make_proj(view, panel_w, panel_h)

    def _inview(lat, lon):
        return view["lo0"] <= lon <= view["lo1"] and view["la0"] <= lat <= view["la1"]

    # confini di stato (tratteggiati)
    if borders:
        for arr, bbox in borders:
            if (bbox[2] < view["lo0"] or bbox[0] > view["lo1"]
                    or bbox[3] < view["la0"] or bbox[1] > view["la1"]):
                continue
            _draw_dashed(d1, proj1(arr), BORDER_COL, 2)
    # nomi degli stati (filigrana) — scala col pannello
    cfont = _font(max(20, panel_w // 48), bold=True)
    for name, anchors in COUNTRIES:
        for lat, lon in anchors:
            if _inview(lat, lon):
                p = proj1(np.array([[lon, lat]]))[0]
                txt = name.upper() if " " in name else " ".join(name.upper())
                d1.text((float(p[0]), float(p[1])), txt, font=cfont, fill=COUNTRY_INK, anchor="mm")
                break
    # nomi isole grandi (scala d'insieme)
    gifont = _font(max(13, panel_w // 82), bold=True, italic=True)
    for name, lat, lon in GLOBAL_ISLANDS:
        if _inview(lat, lon):
            p = proj1(np.array([[lon, lat]]))[0]
            _text_halo(d1, (float(p[0]), float(p[1])), name.upper(), gifont,
                       fill=(120, 105, 80), halo=(255, 255, 255), r=1)

    # etichette viaggi (crisp, anti-collisione) — sopra tutto
    items = []
    for t in trips:
        rp = proj1(smooth_track(t["lonlat"]))
        mid = rp[len(rp) // 2]
        items.append(((float(mid[0]), float(mid[1])), t["name"]))
    _place_labels(d1, panel_w, panel_h, items, _font(17, bold=True))
    return img


def render_global(trips, polys, borders=None):
    med = [t for t in trips if t["region"] == "med"]
    car = [t for t in trips if t["region"] == "caribbean"]
    cuba = [t for t in car if t["lonlat"][:, 0].mean() < -70]
    gren = [t for t in car if t["lonlat"][:, 0].mean() >= -70]

    PANEL_W = 2200
    MARGIN = 60
    GAP = 40
    half_w = (PANEL_W - GAP) // 2
    med_img = _region_panel(med, polys, PANEL_W, borders=borders) if med else None
    cuba_img = _region_panel(cuba, polys, half_w, borders=borders) if cuba else None
    gren_img = _region_panel(gren, polys, half_w, borders=borders) if gren else None
    car_row_h = max([im.height for im in (cuba_img, gren_img) if im] or [0])

    title_h = 116
    cap_h = 52
    legend_rows = math.ceil(len(trips) / 3)
    legend_h = 44 + legend_rows * 34
    total_w = PANEL_W + 2 * MARGIN
    total_h = (title_h + cap_h + (med_img.height if med_img else 0)
               + cap_h + car_row_h + legend_h + MARGIN)
    canvas = Image.new("RGB", (total_w, total_h), PARCHMENT)
    d = ImageDraw.Draw(canvas)
    cfont = _font(30, bold=True)
    subfont = _font(24, bold=True)
    d.text((MARGIN, 38), "Le nostre rotte  ·  2011–2024", font=_font(54, bold=True), fill=INK)

    def frame(panel, x, yy):
        canvas.paste(panel, (x, yy))
        d.rectangle([x, yy, x + panel.width - 1, yy + panel.height - 1], outline=COAST, width=2)

    y = title_h
    d.text((MARGIN, y + 10), "Mediterraneo", font=cfont, fill=INK)
    y += cap_h
    if med_img:
        frame(med_img, MARGIN, y)
        y += med_img.height
    # Caraibi: due riquadri affiancati (Cuba | Piccole Antille)
    d.text((MARGIN, y + 10), "Caraibi", font=cfont, fill=INK)
    y += cap_h
    if cuba_img:
        frame(cuba_img, MARGIN, y)
        _text_halo(d, (MARGIN + 90, y + 24), "Cuba", subfont, fill=INK, halo=(255, 255, 255), r=2)
    if gren_img:
        gx = MARGIN + half_w + GAP
        frame(gren_img, gx, y)
        _text_halo(d, (gx + 150, y + 24), "Piccole Antille", subfont, fill=INK, halo=(255, 255, 255), r=2)
    y += car_row_h

    # legenda (3 colonne, ordine alfabetico) = abbinamento colore->viaggio
    y += 30
    colw = PANEL_W // 3
    lfont = _font(24)
    for i, t in enumerate(trips):
        x = MARGIN + (i % 3) * colw
        yy = y + (i // 3) * 34
        c = tuple(int(t["_hex"][j:j + 2], 16) for j in (1, 3, 5))
        d.rectangle([x, yy + 4, x + 26, yy + 22], fill=c, outline=INK)
        d.text((x + 36, yy + 2), t["name"], font=lfont, fill=INK)

    out = OUT_DIR / "_global.png"
    canvas.save(out, "PNG", optimize=True)
    return out, (total_w, total_h)


# --- main -------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="genera tutti i viaggi (default: pilota)")
    ap.add_argument("--only", action="append", default=[], help="genera solo il viaggio indicato (ripetibile)")
    ap.add_argument("--no-global", action="store_true", help="salta la mappa globale")
    ap.add_argument("--no-labels", action="store_true", help="senza nomi/POI OSM")
    ap.add_argument("--source", default=None, help="KML sorgente alternativo (default: SRC_KML)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    src = Path(args.source) if args.source else SRC_KML
    if not src.exists():
        sys.exit(f"ERRORE: KML sorgente non trovato: {src}")
    trips, trackless = load_trips(src)
    n = len(trips)
    for i, t in enumerate(trips):
        t["_hex"] = kml_color(i, n)[1]

    print(f"Viaggi con traccia: {n}")
    if trackless:
        print("Cartelle SENZA traccia (nessuna immagine):", ", ".join(trackless))

    polys = load_land()
    borders = load_borders()
    print(f"Poligoni costieri caricati: {len(polys)} | segmenti confine: {len(borders)}")

    # selezione per-trip
    if args.only:
        want = {slugify(x) for x in args.only}
        sel = [t for t in trips if t["slug"] in want or t["name"] in args.only]
    elif args.all:
        sel = trips
    else:
        want = {slugify(x) for x in PILOT_TRIPS}
        sel = [t for t in trips if t["slug"] in want]
    mode = "COMPLETO" if args.all else ("ONLY" if args.only else "PILOTA")

    # globale (usa tutti i viaggi)
    if not args.no_global:
        gpath, gsize = render_global(trips, polys, borders)
        print(f"\nGlobale -> {gpath.name}  {gsize[0]}x{gsize[1]}")

    manifest = {}
    print(f"\nPer-trip ({mode}): {len(sel)} viaggi")
    print(f"  {'viaggio':<20} {'punti':>6} {'%suTerra':>9} {'etich':>6}")
    for t in sel:
        meta = render_trip(t, polys, with_labels=not args.no_labels, borders=borders)
        manifest[t["slug"]] = meta
        flag = "  <-- verificare" if meta["on_land_pct"] > 12 else ""
        print(f"  {t['name']:<20} {meta['points']:>6} {meta['on_land_pct']:>8.1f}% {meta.get('labels', 0):>6}{flag}")

    # manifest (accumulo: non perde le voci di run precedenti)
    mf = OUT_DIR / "routes.json"
    existing = {}
    if mf.exists():
        try:
            existing = json.loads(mf.read_text(encoding="utf-8")).get("trips", {})
        except Exception:
            existing = {}
    existing.update(manifest)
    mf.write_text(json.dumps({
        "source": src.name,
        "style": "nautico-chiaro",
        "note": "Immagini in staging. Destinazione sito: site/trips/routes/ (NON site/trips/img). "
                "Gli id-scheda del sito sono slug del nome barca: serve un ponte nome-KML -> boat-id.",
        "global": "_global.png",
        "trackless": trackless,
        "trips": existing,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nManifest -> {mf.name}  ({len(existing)} viaggi totali)")
    print(f"Output in: {OUT_DIR}")


if __name__ == "__main__":
    main()
