"""Shelter Score: una rada e' buona se il vento previsto NON entra dal suo settore aperto.

Semaforo: verde (riparata), giallo (accettabile, monitorare), rosso (esposta).
Il fetch (mare libero a monte) amplifica il problema: 40 km di fetch con 20 kn
fanno onda ben peggiore di 10 km con 20 kn.
"""
from __future__ import annotations
import argparse, math
from core import load, anchorages, in_sector, norm180
import weather


def _dist_to_sector(deg: float, start: float, end: float) -> float:
    """0 se dentro il settore, altrimenti gradi di distanza dal bordo piu' vicino."""
    if in_sector(deg, start, end):
        return 0.0
    return min(abs(norm180(deg - start)), abs(norm180(deg - end)))


SUNSET_BONUS = 6  # punti: spareggia tra rade gia' sicure, non ribalta mai un margine di sicurezza vero


def shelter_score(anch: dict, twd: float, tws: float, gust: float, sunset_az: float | None = None) -> dict:
    margin = _dist_to_sector(twd, anch["exposed_from"], anch["exposed_to"])
    fetch = anch.get("fetch_km", 20)

    if margin == 0:
        # vento dritto in rada: quanto fa male dipende da intensita' e fetch
        exposure = (tws / 25) * (0.5 + min(fetch, 60) / 120)
        score = max(0, round(100 * (1 - min(exposure, 1))))
        light = "rosso" if score < 45 else "giallo"
    else:
        # riparata: bonus crescente con il margine angolare
        score = round(min(100, 55 + margin * 0.5))
        if gust > 30 and margin < 40:
            score -= 15
        light = "verde" if score >= 75 else "giallo"

    if tws < 8:
        score = max(score, 80)
        light = "verde"

    # vista sul tramonto: il settore esposto al vento e' anche il settore con
    # orizzonte libero (nessuna terra in mezzo). Bonus SOLO se la rada e' gia'
    # sicura (light != rosso): mai preferire una rada pericolosa per estetica.
    sunset_view = in_sector(sunset_az, anch["exposed_from"], anch["exposed_to"]) if sunset_az is not None else None
    sunset_bonus = SUNSET_BONUS if (sunset_view and light != "rosso") else 0
    score = min(100, score + sunset_bonus)

    return {
        "id": anch["id"], "name": anch["name"], "score": score, "light": light,
        "margin_deg": round(margin), "fetch_km": fetch,
        "why": (f"vento {twd:.0f}° entra in rada (settore {anch['exposed_from']}-{anch['exposed_to']}°), "
                f"fetch {fetch} km" if margin == 0
                else f"vento {twd:.0f}° a {margin:.0f}° dal settore esposto"),
        "holding": anch.get("holding", "?"), "notes": anch.get("notes", ""),
        "verify": anch.get("verify", False),
        "sunset_view": sunset_view, "sunset_bonus": sunset_bonus,
    }


def rank(twd: float, tws: float, gust: float | None = None, sunset_az: float | None = None) -> list[dict]:
    gust = gust if gust is not None else tws * 1.3
    return sorted((shelter_score(a, twd, tws, gust, sunset_az) for a in anchorages()),
                  key=lambda x: x["score"], reverse=True)


def rank_for_tonight(wp_id: str, day: str, sunset_az: float | None = None) -> list[dict]:
    """Usa la previsione notturna (21:00) del punto dato come riferimento."""
    v = load()
    wp = next(w for w in v["waypoints"] if w["id"] == wp_id)
    series = weather.combined(wp["lat"], wp["lon"], days=5)
    night = next((r for r in series if r["time"].startswith(day) and r["time"].endswith("21:00")), None)
    if not night:
        raise SystemExit("Previsione non disponibile per quella notte")
    return rank(night["twd"], night["tws"], night["gust"], sunset_az), night


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Classifica le rade per il vento previsto")
    ap.add_argument("--twd", type=float, help="direzione vento (da cui viene)")
    ap.add_argument("--tws", type=float, help="intensita' in nodi")
    ap.add_argument("--from-wp", help="id waypoint da cui prendere la previsione")
    ap.add_argument("--day", help="YYYY-MM-DD")
    ap.add_argument("--sunset-az", type=float, help="azimut del tramonto (gradi): bonus vista se coincide col settore aperto")
    a = ap.parse_args()

    if a.from_wp and a.day:
        rows, night = rank_for_tonight(a.from_wp, a.day, a.sunset_az)
        print(f"Notte {a.day}: {night['tws']:.0f} kn da {night['twd']:.0f}° (raffiche {night['gust']:.0f})\n")
    else:
        rows = rank(a.twd, a.tws, sunset_az=a.sunset_az)

    icon = {"verde": "🟢", "giallo": "🟡", "rosso": "🔴"}
    for r in rows:
        tag = " 🌅" if r.get("sunset_view") else ""
        print(f"{icon[r['light']]} {r['score']:>3}  {r['name']:<30}{tag} {r['why']}")
    print("\n" + weather.AM_NOTE)
