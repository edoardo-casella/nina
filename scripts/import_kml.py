"""Importa i segnaposto di una mappa Google My Maps nel voyage.json.

Due modi:
  1. File esportato: My Maps -> menu (tre puntini) -> "Scarica KML" ->
     spuntare "Esporta come KML" (non KMZ).
  2. DIRETTAMENTE dal link della mappa (serve condivisione "chiunque abbia il
     link"): la mappa espone un network-link KML sempre aggiornato, quindi
     ogni run rilegge lo stato corrente della mappa — niente export manuale.

Uso:  python import_kml.py mappa.kml [--merge]
      python import_kml.py "https://www.google.com/maps/d/edit?mid=XXXX" --merge
      python import_kml.py XXXX --merge          # solo il mid

Con --merge i waypoint gia' presenti (stesso id) NON vengono toccati: le
coordinate verificate a mano sopravvivono ai re-import.
"""
from __future__ import annotations
import argparse, re, sys, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
from core import load, save

NS = {"k": "http://www.opengis.net/kml/2.2"}
MID_RE = re.compile(r"[?&]mid=([A-Za-z0-9_-]+)")


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:32]


def kml_source(src: str) -> str:
    """Ritorna il testo KML da un file locale, un URL My Maps o un mid nudo."""
    if not src.startswith("http") and Path(src).exists():
        return Path(src).read_text(encoding="utf-8")
    if src.startswith("http"):
        m = MID_RE.search(src)
        if not m:
            sys.exit("URL senza mid=... : incollare il link della mappa My Maps")
        mid = m.group(1)
    else:
        mid = src  # mid nudo
    url = f"https://www.google.com/maps/d/kml?mid={mid}&forcekml=1"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    if data[:2] == b"PK":
        sys.exit("Ricevuto KMZ nonostante forcekml: scaricare il KML a mano")
    return data.decode("utf-8")


def parse(text: str) -> list[dict]:
    root = ET.fromstring(text)
    out = []
    for pm in root.iter():
        if not pm.tag.endswith("Placemark"):
            continue
        name = next((c.text for c in pm if c.tag.endswith("name")), None)
        point = next((c for c in pm.iter() if c.tag.endswith("Point")), None)
        if not (name and point is not None):
            continue
        coords = next(c.text for c in point if c.tag.endswith("coordinates"))
        lon, lat, *_ = [float(x) for x in coords.strip().split(",")]
        desc = next((c.text for c in pm if c.tag.endswith("description")), "") or ""
        out.append({"id": slug(name), "name": name.strip(), "lat": round(lat, 5),
                    "lon": round(lon, 5), "type": "anchorage",
                    "notes": re.sub(r"<[^>]+>", " ", desc).strip()[:200], "verify": True})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("kml", help="file .kml, URL My Maps o mid della mappa")
    ap.add_argument("--merge", action="store_true")
    a = ap.parse_args()
    wps = parse(kml_source(a.kml))
    if not wps:
        sys.exit("Nessun segnaposto trovato. Il file e' KMZ? Rinominalo .zip ed estrai doc.kml")
    v = load()
    if a.merge:
        have = {w["id"] for w in v["waypoints"]}
        new = [w for w in wps if w["id"] not in have]
        v["waypoints"] += new
        print(f"Aggiunti {len(new)} nuovi waypoint (su {len(wps)} nel KML)")
    else:
        v["waypoints"] = wps
        print(f"Sostituiti tutti i waypoint: {len(wps)}")
    save(v)
    for w in wps[:10]:
        print(f"  {w['id']:<24} {w['lat']:.4f}, {w['lon']:.4f}  {w['name']}")
