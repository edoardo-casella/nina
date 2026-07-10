"""Estrae il CV dello skipper da data/Skipper CV.xlsx e lo serializza in
site/data/skipper.json (COMMITTATO). L'Excel e' gitignorato (data/*.xlsx):
il JSON derivato e' la fonte per site/skipper.html.

Solo il foglio Summary (le crociere): i fogli Passengers/Participations
contengono nomi completi di amici e familiari e NON vanno nel repo pubblico.

  python scripts/build_skipper.py

Le immagini vanno ridimensionate a parte in site/skipper/img/ (vedi commit).
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path

import openpyxl

import core

CV = core.DATA / "Skipper CV.xlsx"
OUT = core.ROOT / "site" / "data" / "skipper.json"
IMG_DIR = core.ROOT / "site" / "skipper" / "img"

NAME = "Edoardo Casella"
INSTAGRAM = "https://www.instagram.com/edoardocasella/"
# ordine di galleria: prima le due migliori, poi droni, poi archivio
GALLERY_ORDER = ["cat-rada-turchese", "kayak-gabbiano", "drone-1", "drone-3",
                 "vela-2017", "caraibi-2017-1", "drone-2", "vela-2016-1",
                 "caraibi-2017-2", "vela-2016-2"]


def num(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def clean_countries(country: str) -> list[str]:
    """'Greece-Turkey', 'Italy - France' -> paesi distinti."""
    return [p.strip() for p in country.replace("&", "-").split("-") if p.strip()]


def load_trips() -> list[dict]:
    wb = openpyxl.load_workbook(CV, data_only=True)
    ws = wb["Summary"]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    idx = {h: i for i, h in enumerate(header)}
    trips = []
    for r in rows[1:]:
        if not r or r[idx.get("Anno", 1)] is None:
            continue
        year = num(r[idx["Anno"]])
        if year is None:                      # riga TOTAL o vuota
            continue
        trips.append({
            "year": int(year),
            "month": str(r[idx["Mese"]]).strip() if r[idx["Mese"]] else None,
            "weeks": str(r[idx["Settimane"]]).strip() if r[idx.get("Settimane")] else None,
            "country": str(r[idx["Country"]]).strip() if r[idx["Country"]] else None,
            "zone": str(r[idx["Zona"]]).strip() if r[idx["Zona"]] else None,
            "boat": str(r[idx["Imbarcazione"]]).strip() if r[idx["Imbarcazione"]] else None,
            "boat_name": str(r[idx["Nome Barca"]]).strip() if r[idx.get("Nome Barca")] else None,
            "nm": round(num(r[idx["Miglia stimate"]]) or 0),
            "days": num(r[idx["Giorni"]]),
        })
    trips.sort(key=lambda t: (t["year"], t.get("month") or ""))
    return trips


def build() -> dict:
    trips = load_trips()
    countries = sorted({c for t in trips for c in clean_countries(t["country"] or "")})
    boats = sorted({t["boat"] for t in trips if t["boat"]})
    totals = {
        "trips": len(trips),
        "nm": sum(t["nm"] for t in trips),
        "days": round(sum(t["days"] or 0 for t in trips), 1),
        "seasons": len({t["year"] for t in trips}),
        "first_year": min(t["year"] for t in trips),
        "last_year": max(t["year"] for t in trips),
        "countries": countries,
        "n_countries": len(countries),
        "n_boats": len(boats),
    }
    imgs = {p.stem: f"skipper/img/{p.name}" for p in IMG_DIR.glob("*.jpg")} if IMG_DIR.exists() else {}
    gallery = [imgs[s] for s in GALLERY_ORDER if s in imgs]
    gallery += [v for k, v in sorted(imgs.items()) if v not in gallery]  # eventuali extra
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "name": NAME, "role": "Skipper", "instagram": INSTAGRAM,
        "totals": totals, "boats": boats, "trips": trips, "gallery": gallery,
    }


if __name__ == "__main__":
    doc = build()
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    t = doc["totals"]
    print(f"Scritto {OUT.name}: {t['trips']} crociere, {t['nm']} nm, "
          f"{t['first_year']}-{t['last_year']}, {t['n_countries']} paesi, "
          f"{len(doc['gallery'])} foto.")
