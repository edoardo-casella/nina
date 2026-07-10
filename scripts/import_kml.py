"""Importa i segnaposto di una mappa Google My Maps nel voyage.json.

Come ottenere il KML:
  My Maps -> menu (tre puntini) -> "Scarica KML" -> spuntare "Esporta come KML"
  (non KMZ). Oppure: .../mymaps?mid=XXXX&output=kml

Uso:  python import_kml.py mappa.kml [--merge]
"""
from __future__ import annotations
import argparse, re, sys, xml.etree.ElementTree as ET
from core import load, save

NS = {"k": "http://www.opengis.net/kml/2.2"}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:32]


def parse(path: str) -> list[dict]:
    root = ET.parse(path).getroot()
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
    ap.add_argument("kml"); ap.add_argument("--merge", action="store_true")
    a = ap.parse_args()
    wps = parse(a.kml)
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
