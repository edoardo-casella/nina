"""Compila vento/mare/miglia dei giorni del diario di bordo (site/data/diario.json).

Miglia: somma haversine dei leg reali del giorno x1.10 (fattore costiero — la
haversine non evita la terraferma, i leg sono gia' spezzati sui capi).
Vento/mare: Open-Meteo con past_days (analisi recente dei modelli; ERA5 su
archive-api arriva con ~5 giorni di ritardo, qui non serve). Finestra 08-19
locali sul punto medio della rotta del giorno. Fonte modellistica, non
osservazioni di bordo: per la calibrazione ECMWF vale solo il logbook
(scripts/logbook.py) col vento osservato.

Uso:
  python scripts/diario_fill.py            # dry-run: stampa le proposte
  python scripts/diario_fill.py --write    # scrive SOLO i campi ancora null
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core
import weather

DIARIO = core.ROOT / "site" / "data" / "diario.json"

# Isola Cavallo non ha un waypoint in voyage.json (il piano non la prevedeva:
# ci e' finito il tender per errore, vedi diario giorno 3) — coordinata locale.
EXTRA = {"cavallo": (41.365, 9.262)}

# Rotta reale di ogni giorno come catena di waypoint id (voyage.json o EXTRA).
LEGS = {
    1: ["cannigione", "spargi"],
    2: ["spargi", "budelli", "cannigione"],
    3: ["cannigione", "lavezzi", "cavallo", "corsica_isola_piana"],
    4: ["corsica_isola_piana", "bonifacio", "cr_roccapina_nord"],
    5: ["cr_roccapina_nord", "capo_senetosa", "capo_di_muro", "isolella"],
}
COASTAL = 1.10  # le rotte vere costeggiano: +10% sulla geodetica
H0, H1 = 8, 19  # finestra "giornata di navigazione", ore locali

COMP = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]


def points(ids: list[str], v: dict) -> list[tuple[float, float]]:
    out = []
    for wid in ids:
        if wid in EXTRA:
            out.append(EXTRA[wid])
        else:
            wp = core.find_wp(v, wid)
            out.append((wp["lat"], wp["lon"]))
    return out


def route_nm(pts: list[tuple[float, float]]) -> int:
    d = sum(core.haversine_nm(a, b) for a, b in zip(pts, pts[1:]))
    return round(d * COASTAL)


def day_hours(hourly: dict, date: str) -> list[int]:
    return [i for i, t in enumerate(hourly["time"])
            if t.startswith(date) and H0 <= int(t[11:13]) <= H1]


def wind_txt(hourly: dict, idx: list[int]) -> str | None:
    spd = [hourly["wind_speed_10m"][i] for i in idx]
    gst = [hourly["wind_gusts_10m"][i] for i in idx]
    dirs = [hourly["wind_direction_10m"][i] for i in idx]
    spd = [s for s in spd if s is not None]
    if not spd:
        return None
    # direzione prevalente: media vettoriale pesata sulla velocita'
    x = sum(s * math.sin(math.radians(d)) for s, d in zip(spd, dirs) if d is not None)
    y = sum(s * math.cos(math.radians(d)) for s, d in zip(spd, dirs) if d is not None)
    comp = COMP[round(math.degrees(math.atan2(x, y)) % 360 / 22.5) % 16]
    lo, hi = round(min(spd)), round(max(spd))
    txt = f"{comp} {lo}-{hi} kn" if lo != hi else f"{comp} {hi} kn"
    gmax = round(max((g for g in gst if g is not None), default=0))
    if gmax >= hi + 5:
        txt += f", raffiche {gmax}"
    return txt


def sea_txt(hourly: dict, idx: list[int]) -> str | None:
    hs = [hourly["wave_height"][i] for i in idx]
    hs = [h for h in hs if h is not None]
    if not hs:
        return None
    h = max(hs)
    # scala Douglas (stato del mare), stessa semantica della Plancia
    stato = ("calmo" if h < 0.1 else "quasi calmo" if h < 0.5 else
             "poco mosso" if h < 1.25 else "mosso" if h < 2.5 else "molto mosso")
    return f"{stato}, {h:.1f} m".replace(".", ",")


def main() -> None:
    write = "--write" in sys.argv
    v = core.load()
    diario = json.loads(DIARIO.read_text(encoding="utf-8"))
    today = __import__("datetime").date.today().isoformat()

    changed = False
    for g in diario["days"]:
        ids = LEGS.get(g["day"])
        if not ids:
            print(f"Giorno {g['day']}: nessuna rotta definita in LEGS, salto")
            continue
        pts = points(ids, v)
        mid = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        # past_days copre l'intera crociera; forecast_days=1 per includere oggi.
        # weather.wind/sea non espongono past_days: si usa il loro _get.
        w = weather._get(weather.FORECAST, {
            "latitude": mid[0], "longitude": mid[1],
            "hourly": "wind_speed_10m,wind_direction_10m,wind_gusts_10m",
            "wind_speed_unit": "kn", "timezone": "Europe/Rome",
            "past_days": 10, "forecast_days": 1, "models": "ecmwf_ifs025"})
        m = weather._get(weather.MARINE, {
            "latitude": mid[0], "longitude": mid[1],
            "hourly": "wave_height", "timezone": "Europe/Rome",
            "past_days": 10, "forecast_days": 1})
        w["hourly"], m["hourly"] = w.get("hourly", {}), m.get("hourly", {})
        prop = {
            "nm": route_nm(pts),
            "wind": wind_txt(w["hourly"], day_hours(w["hourly"], g["date"])),
            "sea": sea_txt(m["hourly"], day_hours(m["hourly"], g["date"])),
        }
        nota = " (giornata in corso: dati parziali)" if g["date"] == today else ""
        print(f"Giorno {g['day']} ({g['date']}) {' -> '.join(ids)}{nota}")
        for k in ("nm", "wind", "sea"):
            cur = g.get(k)
            mark = "SCRIVO" if write and cur is None and prop[k] is not None else \
                   ("tengo" if cur is not None else "proposta")
            print(f"  {k:5} = {prop[k]!r:30} [{mark}, attuale {cur!r}]")
            if write and cur is None and prop[k] is not None:
                g[k] = prop[k]
                changed = True

    if write and changed:
        DIARIO.write_text(json.dumps(diario, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
        print(f"\nScritto {DIARIO}")
    elif write:
        print("\nNiente da scrivere (nessun campo null con proposta valida).")
    else:
        print("\nDry-run: rilancia con --write per compilare i campi null.")


if __name__ == "__main__":
    main()
