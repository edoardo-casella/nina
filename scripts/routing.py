"""Weather router: valuta quanto e' bella (e sicura) una tratta a vela, ora per ora.

Sail Score 0-100. Il punteggio non dice solo "si puo' partire", dice
"vale la pena partire ADESSO invece che tra tre ore o domani".
"""
from __future__ import annotations
import argparse, datetime as dt, math
from core import load, polar, find_wp, haversine_nm, bearing, twa
import weather


def _bell(x: float, best: float, width: float) -> float:
    """1.0 al valore ideale, decade a campana."""
    return math.exp(-((x - best) ** 2) / (2 * width ** 2))


def sail_score(twa_deg: float, tws: float, gust: float, wave: float, boat: dict, pol) -> dict:
    """Ritorna punteggio 0-100 + verdetto + motivo dominante."""
    hard = []
    if tws > boat["max_tws_safe_kn"]:
        hard.append(f"vento {tws:.0f} kn oltre soglia sicurezza ({boat['max_tws_safe_kn']})")
    if gust > boat["max_tws_safe_kn"] * 1.3:
        hard.append(f"raffiche {gust:.0f} kn")
    if wave > boat["max_wave_comfort_m"] * 1.8:
        hard.append(f"onda {wave:.1f} m")
    if hard:
        return {"score": 0, "verdict": "STOP", "boat_kn": 0.0, "mode": "fermi",
                "reason": "; ".join(hard)}

    # Sotto l'angolo minimo di bolina la barca non punta la destinazione:
    # bordeggia, e la velocita' utile e' la VMG, non la velocita' sull'acqua.
    beating = twa_deg < pol.min_twa
    running = twa_deg > 165
    if beating:
        best_twa, vmg = pol.best_upwind(tws)
        ws = pol.speed(best_twa, tws)
        bs, cap, extra = vmg, 40, f"bolina: {best_twa:.0f}° per bordo, VMG {vmg:.1f} kn"
    elif running:
        best_twa, vmg = pol.best_downwind(tws)
        ws = pol.speed(best_twa, tws)
        bs, cap, extra = vmg, 62, f"poppa: meglio strambare a {best_twa:.0f}°"
    else:
        bs, cap, extra = pol.speed(twa_deg, tws), 100, None
        ws = bs

    # regola dello skipper: si va a vela solo se la polare da' almeno
    # min_sail_speed_kn (6.5 sul Dufour 48 cat) di velocita' SULL'ACQUA
    motoring = tws < boat["min_tws_sailing_kn"] or ws < boat.get("min_sail_speed_kn", 3.0)
    if motoring:
        return {"score": round(max(15, 40 - wave * 15)), "verdict": "MOTORE", "boat_kn": boat["cruise_motor_kn"],
                "mode": "motore", "reason": f"vento {tws:.0f} kn insufficiente" if tws < boat["min_tws_sailing_kn"]
                else f"a vela solo {ws:.1f} kn: sotto la soglia dei {boat.get('min_sail_speed_kn', 3.0)} kn"}

    # componenti (0-1)
    angle = _bell(twa_deg, 100, 42)                 # cat: il bello sta fra 70 e 140
    if twa_deg < 55:
        angle *= 0.35                                # i cat non bolinano
    if twa_deg > 165:
        angle *= 0.55                                # poppa piena: lenta e rollante
    strength = _bell(tws, 15, 6)
    if tws > boat["max_tws_comfort_kn"]:
        strength *= 0.5
    comfort = max(0.0, 1 - (wave / (boat["max_wave_comfort_m"] * 1.5)))
    gustiness = 1.0 if tws <= 0 else max(0.4, min(1.0, 1.7 - gust / max(tws, 1)))
    pace = min(1.0, bs / 8.5)

    score = 100 * (0.30 * angle + 0.25 * strength + 0.20 * comfort + 0.10 * gustiness + 0.15 * pace)
    score = min(round(score), cap)

    if score >= 70:
        verdict = "OTTIMA"
    elif score >= 45:
        verdict = "BUONA"
    else:
        verdict = "MEDIOCRE"

    worst = min([("angolo", angle), ("intensita'", strength), ("onda", comfort), ("raffiche", gustiness)], key=lambda x: x[1])
    mode = "bolina" if beating else ("poppa" if running else "vela")
    reason = extra or (f"TWA {twa_deg:.0f}° con {tws:.0f} kn" if score >= 70 else f"limite: {worst[0]}")
    return {"score": score, "verdict": verdict, "boat_kn": bs, "mode": mode, "reason": reason}


def simulate_leg(v, frm: str, to: str, depart_iso: str, series: list[dict]) -> dict:
    """Naviga virtualmente la tratta ora per ora usando la previsione."""
    a, b = find_wp(v, frm), find_wp(v, to)
    total_nm = haversine_nm((a["lat"], a["lon"]), (b["lat"], b["lon"]))
    cog = bearing((a["lat"], a["lon"]), (b["lat"], b["lon"]))
    boat, pol = v["boat"], polar(v)

    idx = next((i for i, r in enumerate(series) if r["time"] >= depart_iso), None)
    if idx is None:
        raise ValueError("Orario di partenza fuori dalla finestra di previsione")

    done, hours, scores, modes, stops = 0.0, 0, [], [], []
    for r in series[idx:idx + 18]:
        angle = twa(r["twd"], cog)
        s = sail_score(angle, r["tws"], r.get("gust", r["tws"]), r.get("wave", 0.3), boat, pol)
        if s["verdict"] == "STOP":
            return {"leg": f"{a['name']} -> {b['name']}", "nm": round(total_nm, 1), "cog": round(cog),
                    "abort": True, "reason": s["reason"], "at": r["time"]}
        speed = s["boat_kn"]
        remaining = total_nm - done
        if speed * 1 >= remaining:
            hours += remaining / speed
            done = total_nm
            scores.append(s["score"]); modes.append(s["mode"])
            break
        done += speed
        hours += 1
        scores.append(s["score"]); modes.append(s["mode"])
        stops.append({"time": r["time"], "twa": round(angle), "tws": r["tws"], "score": s["score"], "mode": s["mode"]})

    eta = dt.datetime.fromisoformat(depart_iso) + dt.timedelta(hours=hours)
    sail_h = sum(1 for m in modes if m != "motore")
    return {
        "leg": f"{a['name']} -> {b['name']}",
        "nm": round(total_nm, 1), "cog": round(cog),
        "depart": depart_iso, "eta": eta.isoformat(timespec="minutes"),
        "hours": round(hours, 1),
        "avg_score": round(sum(scores) / len(scores)) if scores else 0,
        "sail_pct": round(100 * sail_h / max(len(modes), 1)),
        "abort": False,
        "detail": stops,
    }


def best_departure(v, frm: str, to: str, day: str) -> list[dict]:
    """Prova ogni ora della finestra ammessa e ordina per Sail Score."""
    a = find_wp(v, frm)
    series = weather.combined(a["lat"], a["lon"], days=5)
    p = v["preferences"]
    h0 = int(p["earliest_departure"][:2])
    h1 = int(p["latest_anchor_time"][:2]) - 1
    out = []
    for h in range(h0, h1):
        depart = f"{day}T{h:02d}:00"
        try:
            r = simulate_leg(v, frm, to, depart, series)
        except ValueError:
            continue
        if r["abort"]:
            out.append({"depart": depart, "avg_score": 0, "note": "STOP: " + r["reason"]})
            continue
        arr = dt.datetime.fromisoformat(r["eta"])
        if arr.strftime("%H:%M") > p["latest_anchor_time"] and arr.date().isoformat() == day:
            r["note"] = "arrivo oltre l'orario di ancoraggio"
            r["avg_score"] -= 20
        out.append(r)
    return sorted(out, key=lambda x: x["avg_score"], reverse=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Valuta una tratta")
    ap.add_argument("frm"); ap.add_argument("to")
    ap.add_argument("--day", default=dt.date.today().isoformat())
    args = ap.parse_args()
    v = load()
    for r in best_departure(v, args.frm, args.to, args.day)[:5]:
        print(f"{r['depart']}  score {r['avg_score']:>3}  "
              f"{r.get('hours','-')} h  vela {r.get('sail_pct','-')}%  {r.get('note','')}")
    print("\n" + weather.AM_NOTE)
