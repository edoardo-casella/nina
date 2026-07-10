"""Genera i tre JSON che la dashboard legge. Girato da GitHub Actions due volte al
giorno (12:00 e 20:00 Europe/Rome) e da riga di comando quando serve.

  python scripts/publish.py                 # oggi, meteo reale
  python scripts/publish.py --day 2026-08-12
  python scripts/publish.py --offline       # vento sintetico, per sviluppare senza rete

Il piano esce sempre con "approved": false. La dashboard lo mostra come PROPOSTA
finche' qualcuno non mette "approved": true in site/data/briefing.json (o non lancia
publish.py --approve). Il meteo e' un fatto e si aggiorna da solo; il piano e' una
decisione e ha bisogno di un nome sopra.
"""
from __future__ import annotations
import argparse, datetime as dt, json, math, sys
from pathlib import Path

import core, routing, shelter, ledger, weather

SITE = core.ROOT / "site" / "data"
LIGHTS = {"OTTIMA": "verde", "BUONA": "verde", "MEDIOCRE": "giallo", "MOTORE": "giallo", "STOP": "rosso"}


def synth(day: str, hours: int = 72) -> list[dict]:
    """Maestrale finto che rinforza nel pomeriggio. Solo per sviluppo offline."""
    d0 = dt.datetime.fromisoformat(day + "T00:00")
    out = []
    for h in range(hours):
        t = d0 + dt.timedelta(hours=h)
        diurnal = math.sin(max(0, (t.hour - 6)) / 14 * math.pi)
        tws = 8 + 11 * max(diurnal, 0) + 2 * math.sin(h / 17)
        out.append({"time": t.isoformat(timespec="minutes"), "tws": round(tws, 1),
                    "twd": round(305 + 18 * math.sin(h / 23), 0), "gust": round(tws * 1.32, 1),
                    "wave": round(0.2 + tws / 30, 2), "wave_dir": round(290 + 15 * math.sin(h / 19), 0),
                    "rain": 0, "temp": round(23 + 6 * max(diurnal, 0), 1), "rh": round(70 - 15 * max(diurnal, 0)),
                    "wmo": 0 if h % 30 < 24 else 3})
    return out


# fase in gradi -> nome ed emoji (0 nuova, 90 primo quarto, 180 piena, 270 ultimo)
MOON_NAMES = ["Luna nuova", "Crescente", "Primo quarto", "Gibbosa crescente",
              "Luna piena", "Gibbosa calante", "Ultimo quarto", "Calante"]
MOON_EMOJI = ["\U0001F311", "\U0001F312", "\U0001F313", "\U0001F314",
              "\U0001F315", "\U0001F316", "\U0001F317", "\U0001F318"]


def moon_info(deg: float | None) -> dict:
    if deg is None:
        return {"name": None, "emoji": None, "illum_pct": None}
    i = int(((deg + 22.5) % 360) // 45)
    return {"name": MOON_NAMES[i], "emoji": MOON_EMOJI[i],
            "illum_pct": round((1 - math.cos(math.radians(deg))) / 2 * 100)}


def synth_moon_deg(day: str) -> float:
    """Fase lunare calcolata (novilunio di riferimento 2000-01-06): niente rete."""
    ref = dt.datetime(2000, 1, 6, 18, 14)
    age = (dt.datetime.fromisoformat(day + "T12:00") - ref).total_seconds() / 86400 % 29.530588
    return age / 29.530588 * 360


def build_astro(wp: dict, day: str, offline: bool) -> list[dict]:
    if offline:
        deg = synth_moon_deg(day)
        days = []
        for i in range(4):
            d = (dt.date.fromisoformat(day) + dt.timedelta(days=i)).isoformat()
            days.append({"date": d, "sunrise": "06:32", "sunset": "20:41",
                         "moonrise": "21:15", "moonset": "07:05",
                         "moon_deg": (deg + i * 12.2) % 360, "synthetic": True})
    else:
        days = weather.sun_moon(wp["lat"], wp["lon"], day)
    for r in days:
        r.update(moon_info(r.get("moon_deg")))
    return days


def leg_for(v: dict, day: str) -> dict | None:
    return next((p for p in v["plan"] if p["date"] == day), None)


def sim_shift_days(v: dict, today: str) -> int:
    """Fuori dalle date della crociera la dashboard gira in SIMULAZIONE:
    il piano reale viene traslato come se si partisse oggi. Ritorna l'offset
    in giorni da applicare alle date del piano (0 = crociera in corso)."""
    if not v["plan"]:
        return 0
    t = dt.date.fromisoformat(today)
    d0 = dt.date.fromisoformat(v["plan"][0]["date"])
    d1 = dt.date.fromisoformat(v["plan"][-1]["date"])
    if d0 <= t <= d1:
        return 0
    return (t - d0).days


def shifted_plan(v: dict, offset: int) -> list[dict]:
    if not offset:
        return v["plan"]
    return [{**p, "date": (dt.date.fromisoformat(p["date"]) + dt.timedelta(days=offset)).isoformat()}
            for p in v["plan"]]


def andatura(twa_deg: float) -> str:
    if twa_deg < 55:
        return "bolina"
    if twa_deg < 80:
        return "bolina larga"
    if twa_deg < 110:
        return "traverso"
    if twa_deg < 150:
        return "lasco"
    return "poppa"


def sailing_estimate(v: dict, frm: dict, to: dict, tws: float, twd: float) -> dict:
    """Vela o motore per una tratta, dal vento previsto e dalla polare.

    Regola dello skipper: si va a vela quando l'andatura e' da bolina larga
    in giu' (TWA >= 55) e la polare da' almeno min_sail_speed_kn (6.5 kn sul
    Dufour 48 cat); altrimenti motore a cruise_motor_kn."""
    cog = core.bearing((frm["lat"], frm["lon"]), (to["lat"], to["lon"]))
    twa = core.twa(twd, cog)
    pol = core.polar(v)
    bs = pol.speed(twa, tws)
    boat = v["boat"]
    vela = (tws >= boat["min_tws_sailing_kn"] and twa >= 55
            and bs >= boat.get("min_sail_speed_kn", 4.0))
    return {"twa": round(twa), "andatura": andatura(twa),
            "vela": bool(vela), "boat_kn": bs if vela else boat["cruise_motor_kn"],
            "tws_est": round(tws, 1), "twd": round(twd)}


def build_outlook(v: dict, plan: list[dict], day: str, days: int, offline: bool) -> list[dict]:
    """Un giorno per riga: tratta, meteo previsto NELLA destinazione, stima
    vela/motore. Il vento usato per l'andatura e' il dominante giornaliero:
    e' una stima, non un routing."""
    rows = []
    for i in range(1, days + 1):
        d = (dt.date.fromisoformat(day) + dt.timedelta(days=i)).isoformat()
        p = leg_for({"plan": plan}, d)
        if not p:
            continue
        a, b = core.find_wp(v, p["from"]), core.find_wp(v, p["to"])
        rows.append({"date": d, "plan": p, "frm": a, "to": b})
    if not rows:
        return []

    dailies = [None] * len(rows)
    if not offline:
        try:
            resp = weather.daily_at([(r["to"]["lat"], r["to"]["lon"]) for r in rows],
                                    rows[0]["date"], rows[-1]["date"])
            dailies = [resp[i] if i < len(resp) else None for i in range(len(rows))]
        except Exception:
            pass

    out = []
    for r, met in zip(rows, dailies):
        p, a, b = r["plan"], r["frm"], r["to"]
        nm = core.haversine_nm((a["lat"], a["lon"]), (b["lat"], b["lon"]))
        row = {"date": r["date"], "rest": p["rest"],
               "frm": a["name"], "to": b["name"], "nm": round(nm, 1)}
        wx_day = None
        if met:
            try:
                j = met["daily"]["time"].index(r["date"])
                dd = met["daily"]
                wx_day = {"wmo": dd["weather_code"][j], "tmax": dd["temperature_2m_max"][j],
                          "tmin": dd["temperature_2m_min"][j], "rain_mm": dd["precipitation_sum"][j],
                          "rain_prob": dd["precipitation_probability_max"][j],
                          "wind_max": dd["wind_speed_10m_max"][j], "gust_max": dd["wind_gusts_10m_max"][j],
                          "wind_dir": dd["wind_direction_10m_dominant"][j]}
            except Exception:
                wx_day = None
        if offline:
            wx_day = {"wmo": 1, "tmax": 29, "tmin": 22, "rain_mm": 0, "rain_prob": 5,
                      "wind_max": 16, "gust_max": 22, "wind_dir": 305, "synthetic": True}
        row["wx"] = wx_day
        if wx_day and not p["rest"]:
            # vento tipico di giornata ~ 80% del massimo
            row["sailing"] = sailing_estimate(v, a, b, wx_day["wind_max"] * 0.8, wx_day["wind_dir"])
        else:
            row["sailing"] = None
        out.append(row)
    return out


def build(day: str, offline: bool) -> tuple[dict, dict, dict]:
    v = core.load()
    offset = sim_shift_days(v, day)
    plan_all = shifted_plan(v, offset)
    plan = leg_for({"plan": plan_all}, day)
    start_id = plan["from"] if plan else v["waypoints"][0]["id"]
    wp = core.find_wp(v, start_id)

    if offline:
        series = synth(day)
        conf = {"confidence": "n/d (offline)", "mean_spread_kn": None}
    else:
        series = weather.combined(wp["lat"], wp["lon"], days=4)
        try:
            conf = weather.ensemble_spread(wp["lat"], wp["lon"])
        except Exception as e:
            conf = {"confidence": "sconosciuta", "error": str(e)}

    # ---- tratta di oggi
    leg, options = None, []
    if plan and not plan["rest"]:
        _real = weather.combined
        weather.combined = lambda *a, **k: series          # riusa la serie gia' scaricata
        try:
            options = routing.best_departure(v, plan["from"], plan["to"], day)[:3]
            # gli STOP entrano in classifica come stub senza leg/eta:
            # mai darli alla dashboard come tratta del giorno
            leg = next((o for o in options if o.get("leg")), None)
        finally:
            weather.combined = _real

    # ---- rada di stanotte
    night = next((r for r in series if r["time"].startswith(day) and r["time"][11:] == "21:00"), series[min(21, len(series) - 1)])
    dest = plan["to"] if plan else start_id
    ranked = shelter.rank(night["twd"], night["tws"], night.get("gust", night["tws"] * 1.3))
    tonight = next((r for r in ranked if r["id"] == dest), None)
    plan_b = next((r for r in ranked if r["id"] != dest and r["light"] == "verde"), None)

    # ---- prossimi giorni: meteo nella destinazione + stima vela/motore
    outlook = build_outlook(v, plan_all, day, 5, offline)

    # ---- andatura di oggi (dal routing orario della tratta scelta)
    leg_sailing = None
    if leg:
        if leg.get("detail"):
            sail_rows = [r for r in leg["detail"] if r["mode"] != "motore"]
            twas = sorted(r["twa"] for r in (sail_rows or leg["detail"]))
            med = twas[len(twas) // 2]
            leg_sailing = {"andatura": andatura(med), "twa": med,
                           "vela": bool(sail_rows),
                           "avg_kn": round(leg["nm"] / leg["hours"], 1) if leg.get("hours") else None}
        else:
            # tratta cosi' corta da chiudersi nella prima ora: stima dal vento alla partenza
            dep = next((r for r in series if r["time"] >= leg["depart"]), None)
            if dep:
                est = sailing_estimate(v, core.find_wp(v, plan["from"]), core.find_wp(v, plan["to"]),
                                       dep["tws"], dep["twd"])
                leg_sailing = {"andatura": est["andatura"], "twa": est["twa"], "vela": est["vela"],
                               "avg_kn": round(leg["nm"] / leg["hours"], 1) if leg.get("hours") else est["boat_kn"]}

    # in simulazione l'equipaggio e' quello della data reale corrispondente
    orig_day = (dt.date.fromisoformat(day) - dt.timedelta(days=offset)).isoformat()
    crew = core.aboard_on(v, orig_day)
    # offset esplicito: i telefoni fuori dal fuso italiano devono leggere
    # l'eta' del dato giusta
    now = dt.datetime.now().astimezone().isoformat(timespec="minutes")

    briefing = {
        "generated_at": now, "approved": False, "approved_by": None,
        "day": day, "boat": v["boat"]["name"], "voyage": v["name"],
        "captains": v.get("captains", []),
        "sim": bool(offset), "cruise_start": v["plan"][0]["date"] if v["plan"] else None,
        "position": {"id": wp["id"], "name": wp["name"]},
        "rest": bool(plan and plan["rest"]),
        "leg": leg, "leg_sailing": leg_sailing, "options": options, "confidence": conf,
        "stop_reason": (options[0].get("note") if options and leg is None else None),
        "tonight": tonight, "plan_b": plan_b, "ranked": ranked[:4],
        "outlook": outlook,
        "crew": [{"name": m["name"], "role": m["role"]} for m in crew],
        "turns": {"cambusa": crew[len(crew) // 2]["name"] if crew else None,
                  "cucina": crew[0]["name"] if crew else None,
                  "tender": crew[-1]["name"] if crew else None},
        "source": "Open-Meteo (ECMWF) — non ufficiale",
        "official": "https://www.meteoam.it/it/mare",
    }
    # 48 ore DA ADESSO: senza questo taglio, al run delle 20:00 il ribbon
    # mostrerebbe 20 colonne di passato e solo 28 di previsione
    cur_hour = now[:13] + ":00"
    start = next((i for i, r in enumerate(series) if r["time"] >= cur_hour), 0)
    now_row = series[start] if start < len(series) else None
    briefing["now"] = ({"temp": now_row.get("temp"), "rh": now_row.get("rh"),
                        "rain": now_row.get("rain"), "wmo": now_row.get("wmo"),
                        "tws": now_row.get("tws"), "twd": now_row.get("twd")}
                       if now_row else None)
    try:
        astro = build_astro(wp, day, offline)
    except Exception:
        astro = []          # niente effemeridi non deve mai bloccare il briefing
    wx = {"generated_at": now, "waypoint": wp["name"], "hours": series[start:start + 48],
          "astro": astro}
    sh = ledger.shares(v)
    st = ledger.settle(v)
    conti = {"generated_at": now, "person_nights": sh["total_person_nights"],
             "per_person": list(sh["per_person"].values()),
             "spent": st["total_spent"],
             "transfers": [{"from": next(m["name"] for m in v["crew"] if m["id"] == t["from"]),
                            "to": next(m["name"] for m in v["crew"] if m["id"] == t["to"]),
                            "amount": t["amount"]} for t in st["transfers"]]}
    return briefing, wx, conti


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=dt.date.today().isoformat())
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--approve", metavar="NOME", help="marca il piano come approvato da NOME")
    a = ap.parse_args()

    SITE.mkdir(parents=True, exist_ok=True)
    if a.approve:
        p = SITE / "briefing.json"
        b = json.loads(p.read_text(encoding="utf-8"))
        b["approved"], b["approved_by"] = True, a.approve
        p.write_text(json.dumps(b, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Piano del {b['day']} approvato da {a.approve}")
        sys.exit(0)

    briefing, wx, conti = build(a.day, a.offline)
    for name, obj in (("briefing", briefing), ("weather", wx), ("conti", conti)):
        (SITE / f"{name}.json").write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    tag = briefing["leg"]["leg"] if briefing["leg"] else ("sosta" if briefing["rest"] else "—")
    print(f"Pubblicato {a.day}: {tag} | score {briefing['leg']['avg_score'] if briefing['leg'] else '—'} "
          f"| rada {briefing['tonight']['name'] if briefing['tonight'] else '—'} "
          f"({briefing['tonight']['light'] if briefing['tonight'] else '?'})")
