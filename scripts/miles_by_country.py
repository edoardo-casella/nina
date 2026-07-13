# -*- coding: utf-8 -*-
# Attribuzione miglia PER PAESE sui viaggi multi-paese, dai tracciati GPS di Google
# Earth (data/Viaggi in barca (2011-2024)_last.kml). Per ogni tratta del tracciato
# assegna le miglia al paese piu' vicino (nearest-country sui poligoni Natural Earth
# 10m): dentro un poligono = distanza 0, altrimenti distanza minima alla costa. Dal
# tracciato ricava la PROPORZIONE per paese, che applica al totale UFFICIALE del
# viaggio (Excel/trips.json) cosi' la somma per paese resta esattamente il totale.
# Output: data/miles-by-country.json (audit) + inietta nm_by_country in site/data/trips.json.
# One-off locale: usa numpy (niente shapely). I confini Natural Earth sono in
# data/geo/ (gitignored) e non servono in CI.
import json, os, io, re, sys
import xml.etree.ElementTree as ET
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KML = os.path.join(ROOT, "data", "Viaggi in barca (2011-2024)_last.kml")
GEO = os.path.join(ROOT, "data", "geo", "ne_10m_admin_0_countries.geojson")
TRIPS = os.path.join(ROOT, "site", "data", "trips.json")
AUDIT = os.path.join(ROOT, "data", "miles-by-country.json")

R_NM = 3440.065
def haversine_nm(lat1, lon1, lat2, lon2):
    p = np.pi / 180.0
    a = (np.sin((lat2 - lat1) * p / 2) ** 2 +
         np.cos(lat1 * p) * np.cos(lat2 * p) * np.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * R_NM * np.arcsin(np.sqrt(a))

# --- token paese (come in trips.json) -> ADMIN Natural Earth ------------------
NE_ADMIN = {
    "Italy": "Italy", "France": "France", "Greece": "Greece", "Turkey": "Turkey",
    "Saint Vincent": "Saint Vincent and the Grenadines", "Saint Lucia": "Saint Lucia",
}

# --- viaggio -> folder KML candidato/i (normalizzati) -------------------------
# stephanie 2012 e' ambiguo (due tracce 2012): si prova entrambe e si tiene quella
# che tocca davvero la Turchia (l'altra 2012 e' natfika, monopaese Grecia).
def fkey(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())
TRIP_FOLDER = {
    "stephanie": ["dodecaneso12", "cyclades12"],
    "klaudia":   ["turkey13"],
    "sorbe":     ["caribe17"],
    "alba":      ["sardegna20"],
    "enya":      ["corsica21"],
}

# --- KML: folder -> array (lon,lat) ------------------------------------------
def local(tag): return tag.split("}")[-1]
def coords_np(text):
    pts = []
    for tok in (text or "").split():
        c = tok.split(",")
        if len(c) >= 2:
            try: pts.append((float(c[0]), float(c[1])))
            except ValueError: pass
    return np.array(pts, dtype=float) if pts else np.zeros((0, 2))

def load_kml_tracks(path):
    root = ET.parse(path).getroot()
    tracks = {}
    def walk(el, folder):
        for ch in el:
            t = local(ch.tag)
            if t == "Folder":
                nm = ""
                for c in ch:
                    if local(c.tag) == "name": nm = (c.text or "").strip()
                walk(ch, nm or folder)
            elif t == "Placemark":
                arr = np.zeros((0, 2))
                for ls in ch.iter():
                    if local(ls.tag) in ("LineString", "LinearRing"):
                        for c in ls:
                            if local(c.tag) == "coordinates":
                                a = coords_np(c.text)
                                if len(a) > len(arr): arr = a
                if len(arr) and folder:
                    k = fkey(folder)
                    if len(arr) > len(tracks.get(k, np.zeros((0, 2)))): tracks[k] = arr
            else:
                walk(ch, folder)
    walk(root, "")
    return tracks

# --- Natural Earth: ADMIN -> lista di poligoni [(ext lonlat, [holes lonlat])] --
def rings_of(geom):
    polys = []
    if geom["type"] == "Polygon":
        rings = [np.array(r, dtype=float)[:, :2] for r in geom["coordinates"]]
        polys.append((rings[0], rings[1:]))
    elif geom["type"] == "MultiPolygon":
        for poly in geom["coordinates"]:
            rings = [np.array(r, dtype=float)[:, :2] for r in poly]
            polys.append((rings[0], rings[1:]))
    return polys

def load_countries(path, admins):
    d = json.load(io.open(path, encoding="utf-8"))
    want = {a.upper() for a in admins}
    out = {}
    for f in d["features"]:
        p = f["properties"]
        adm = (p.get("ADMIN") or p.get("admin") or "")
        if adm.upper() in want:
            out[adm] = rings_of(f["geometry"])
    return out

# --- proiezione equirettangolare locale (nm) + geometria ----------------------
def projector(lat0, lon0):
    kx = 60.0 * np.cos(np.radians(lat0))
    ky = 60.0
    return lambda lonlat: np.column_stack(((lonlat[:, 0] - lon0) * kx, (lonlat[:, 1] - lat0) * ky))

def pt_in_poly(pt, ring):  # ray-cast in piano proiettato; ring Nx2
    x, y = pt; n = len(ring); inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]; xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi):
            inside = not inside
        j = i
    return inside

def min_dist_to_ring(pt, ring):  # distanza minima punto-segmento (piano), ring Nx2 proiettato
    A = ring[:-1]; B = ring[1:]
    if len(A) == 0: return np.inf
    AB = B - A; AP = pt - A
    denom = (AB[:, 0] ** 2 + AB[:, 1] ** 2)
    t = np.where(denom > 0, (AP[:, 0] * AB[:, 0] + AP[:, 1] * AB[:, 1]) / np.where(denom > 0, denom, 1), 0.0)
    t = np.clip(t, 0.0, 1.0)
    proj = A + t[:, None] * AB
    d = np.hypot(pt[0] - proj[:, 0], pt[1] - proj[:, 1])
    return d.min()

def country_distance(pt, polys_proj):  # 0 se dentro un poligono (fuori dai buchi), altrimenti dist costa
    best = np.inf
    for ext, holes in polys_proj:
        if pt_in_poly(pt, ext) and not any(pt_in_poly(pt, h) for h in holes):
            return 0.0
        best = min(best, min_dist_to_ring(pt, ext))
        for h in holes:
            best = min(best, min_dist_to_ring(pt, h))
    return best

def attribute(track, countries, cand_tokens, margin_deg=3.0):
    lat0 = float(track[:, 1].mean()); lon0 = float(track[:, 0].mean())
    proj = projector(lat0, lon0)
    tp = proj(track)
    # prefiltra i poligoni al bbox del tracciato + margine (scarta es. la Francia
    # continentale per la tappa caraibica) e proietta
    lo = track.min(0) - margin_deg; hi = track.max(0) + margin_deg
    cpoly = {}
    for tok in cand_tokens:
        adm = NE_ADMIN[tok]; polys = countries.get(adm, [])
        kept = []
        for ext, holes in polys:
            inb = ((ext[:, 0] >= lo[0]) & (ext[:, 0] <= hi[0]) &
                   (ext[:, 1] >= lo[1]) & (ext[:, 1] <= hi[1]))
            if inb.any():
                kept.append((proj(ext), [proj(h) for h in holes]))
        cpoly[tok] = kept
    # per ogni tratta: miglia al paese del midpoint (nearest-country)
    nm_by = {tok: 0.0 for tok in cand_tokens}
    seglen = haversine_nm(track[:-1, 1], track[:-1, 0], track[1:, 1], track[1:, 0])
    mid = (tp[:-1] + tp[1:]) / 2.0
    per_seg = []
    for i in range(len(seglen)):
        dists = {tok: country_distance(mid[i], cpoly[tok]) for tok in cand_tokens}
        who = min(dists, key=lambda k: dists[k])
        nm_by[who] += float(seglen[i]); per_seg.append(who)
    total = float(seglen.sum())
    return nm_by, total, {"lat0": lat0, "lon0": lon0,
                          "rings_kept": {t: len(cpoly[t]) for t in cand_tokens}}

def split_official(nm_by, total_track, official_nm):
    # applica le proporzioni del tracciato al totale ufficiale; aggiusta il resto
    if total_track <= 0: return {}
    frac = {c: nm_by[c] / total_track for c in nm_by}
    raw = {c: official_nm * frac[c] for c in frac}
    out = {c: int(round(raw[c])) for c in raw}
    diff = official_nm - sum(out.values())
    if diff != 0 and out:  # aggiusta al paese con quota maggiore
        k = max(out, key=lambda c: raw[c]); out[k] += diff
    return out

def main():
    tracks = load_kml_tracks(KML)
    trips = json.load(io.open(TRIPS, encoding="utf-8"))
    by_id = {t["id"]: t for t in trips["trips"]}
    admins = sorted(set(NE_ADMIN.values()))
    countries = load_countries(GEO, admins)
    print("paesi caricati:", {a: len(countries.get(a, [])) for a in admins})

    audit = {}
    for tid, folders in TRIP_FOLDER.items():
        t = by_id.get(tid)
        if not t: print("!! trip mancante:", tid); continue
        toks = [x.strip() for x in re.split(r"[-&]", t["country"]) if x.strip()]
        toks = [x for x in toks if x in NE_ADMIN]
        official = int(t["nm"])
        # scegli la traccia: fra i folder candidati, quella che copre piu' km e (per
        # gli ambigui) che tocca davvero il 2o paese
        best = None
        for fk in folders:
            if fk not in tracks: continue
            nm_by, total, meta = attribute(tracks[fk], countries, toks)
            secondary = sorted(toks, key=lambda c: nm_by.get(c, 0))[0]  # paese meno gettonato
            score = (nm_by.get(secondary, 0) > 1.0, total)  # preferisci chi tocca il 2o paese
            if best is None or score > best[0]:
                best = (score, fk, nm_by, total, meta)
        if best is None:
            print("!! nessuna traccia per", tid, folders); continue
        _, fk, nm_by, total, meta = best
        nm_out = split_official(nm_by, total, official)
        audit[tid] = {"folder": fk, "official_nm": official, "track_nm": round(total, 1),
                      "track_nm_by_country": {c: round(v, 1) for c, v in nm_by.items()},
                      "nm_by_country": nm_out, "rings_kept": meta["rings_kept"]}
        print(f"\n{tid}  ({t['country']})  ufficiale {official} nm  | traccia '{fk}' {total:.0f} nm")
        for c in toks:
            print(f"    {c:16s}  traccia {nm_by.get(c,0):6.1f} nm  ->  {nm_out.get(c,0):4d} nm  ({100*nm_by.get(c,0)/total:4.1f}%)")

    # scrivi audit
    out = {"generated_at": "2026-07-14",
           "method": "nearest-country su tracciati GPS Google Earth (Natural Earth 10m), "
                     "proporzione applicata al totale ufficiale del viaggio",
           "source_kml": "data/Viaggi in barca (2011-2024)_last.kml",
           "trips": audit}
    io.open(AUDIT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=2))
    print("\nscritto", AUDIT)

    # inietta in trips.json (post-processing chirurgico: NON tocca le foto)
    if "--write-trips" in sys.argv:
        for tid, a in audit.items():
            by_id[tid]["nm_by_country"] = a["nm_by_country"]
        io.open(TRIPS, "w", encoding="utf-8").write(json.dumps(trips, ensure_ascii=False, indent=2))
        print("iniettato nm_by_country in", TRIPS)

if __name__ == "__main__":
    main()
