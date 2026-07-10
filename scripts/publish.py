"""Genera i quattro JSON che la dashboard legge (briefing, weather, conti,
program). Girato da GitHub Actions due volte al giorno (12:00 e 20:00
Europe/Rome) e da riga di comando quando serve.

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

import core, routing, shelter, ledger, weather, photos

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


_PHOTOS: dict[str, dict | None] = {}


_PREV_PHOTOS: dict[str, dict] | None = None


def _prev_photos() -> dict[str, dict]:
    """Foto dell'ultimo program.json pubblicato: se Commons rate-limita il
    runner CI (IP condivisi), si riusa l'ultima foto buona invece di perderla."""
    global _PREV_PHOTOS
    if _PREV_PHOTOS is None:
        try:
            prev = json.loads((SITE / "program.json").read_text(encoding="utf-8"))
            _PREV_PHOTOS = {d["id"]: d["photo"]
                            for d in prev.get("destinations", []) if d.get("photo")}
        except Exception:
            _PREV_PHOTOS = {}
    return _PREV_PHOTOS


def photo_ref(wp: dict, offline: bool) -> dict | None:
    """Foto Commons del waypoint, memoizzata per run. Mai bloccante."""
    if offline:
        return None
    if wp["id"] not in _PHOTOS:
        try:
            p = photos.photo_for(wp["lat"], wp["lon"], wp["name"])
        except Exception:
            p = None
        _PHOTOS[wp["id"]] = p or _prev_photos().get(wp["id"])
    return _PHOTOS[wp["id"]]


def norm_steps(p: dict) -> list[dict]:
    """Un giorno puo' avere fino a 3 tappe esplicite in `steps` (rada mattina,
    pomeriggio, sera). I giorni in formato vecchio (solo from/to) diventano
    un'unica tappa sintetica: le due forme convivono, day-level resta autorita'."""
    if p.get("steps"):
        return p["steps"]
    return [{"slot": "giornata", "from": p["from"], "to": p["to"],
             "activity": [], "night_stay": not p.get("night"), "verify": False}]


def slot_depart(step: dict, prefs: dict) -> str:
    """Orario di partenza della tappa: esplicito se c'e', altrimenti default
    di slot (mattina = earliest_departure)."""
    if step.get("depart_at"):
        return step["depart_at"]
    return {"pomeriggio": "13:00", "sera": "16:00"}.get(
        step.get("slot"), prefs.get("earliest_departure", "08:00"))


def build_day_steps(v: dict, p: dict, day: str, series: list[dict],
                    offline: bool) -> list[dict]:
    """Le tappe del giorno, ognuna con il suo routing orario. Approssimazione
    dichiarata: un'unica serie meteo (scaricata alla posizione di inizio
    giornata) per tutte le tappe — a <=30 nm/giorno l'errore e' piccolo."""
    prefs = v.get("preferences", {})
    out = []
    for s in norm_steps(p):
        a, b = core.find_wp(v, s["from"]), core.find_wp(v, s["to"])
        meta = {"slot": s.get("slot", "giornata"), "activity": s.get("activity", []),
                "night_stay": bool(s.get("night_stay")), "verify": bool(s.get("verify")),
                "arrive_by": s.get("arrive_by"), "frm_id": s["from"], "to_id": s["to"],
                "rating": b.get("rating"), "photo": photo_ref(b, offline)}
        if s["from"] == s["to"]:
            out.append({**meta, "stay": True, "name": b["name"], "nm": 0})
            continue
        hh = slot_depart(s, prefs)
        try:
            r = routing.simulate_leg(v, s["from"], s["to"], f"{day}T{hh}", series)
        except ValueError:
            # partenza fuori dalla finestra di previsione: resta la geometria
            r = {"leg": f"{a['name']} -> {b['name']}",
                 "nm": round(core.haversine_nm((a["lat"], a["lon"]), (b["lat"], b["lon"])), 1),
                 "cog": round(core.bearing((a["lat"], a["lon"]), (b["lat"], b["lon"]))),
                 "abort": None, "reason": "fuori dalla finestra di previsione"}
        out.append({**r, **meta, "stay": False, "frm": a["name"], "to": b["name"]})
    return out


def confidence_tier(days_ahead: int) -> str:
    """Fascia di affidabilita' della previsione giornaliera: entro ~7 giorni
    piena, 8-10 degradata, oltre resta solo il programma."""
    if days_ahead <= 7:
        return "piena"
    if days_ahead <= 10:
        return "degradata"
    return "programma"


TIER_LEGEND = {"piena": "previsione affidabile (fino a ~7 giorni)",
               "degradata": "affidabilita' ridotta (8-10 giorni)",
               "programma": "solo programma: oltre l'orizzonte di previsione"}


def build_program(v: dict, plan_all: list[dict], day: str, offset: int,
                  offline: bool, now: str) -> dict:
    """Le prossime due settimane lungo la rotta, un giorno per riga: tappe,
    miglia, cambi equipaggio, e meteo dove la previsione arriva davvero
    (fascia `tier`). Le miglia sono haversine: e' un programma, non un routing."""
    d0 = dt.date.fromisoformat(day)
    rows = []
    for i in range(14):
        d = (d0 + dt.timedelta(days=i)).isoformat()
        p = leg_for({"plan": plan_all}, d)
        if not p:
            continue
        tappe, tot = [], 0.0
        for s in norm_steps(p):
            a, b = core.find_wp(v, s["from"]), core.find_wp(v, s["to"])
            nm = 0.0 if s["from"] == s["to"] else core.haversine_nm(
                (a["lat"], a["lon"]), (b["lat"], b["lon"]))
            tot += nm
            tappe.append({"slot": s.get("slot", "giornata"), "to": b["name"],
                          "to_id": s["to"], "nm": round(nm, 1),
                          "activity": s.get("activity", []),
                          "rating": b.get("rating"), "verify": bool(s.get("verify"))})
        # in simulazione i cambi equipaggio seguono le date VERE, non quelle shiftate
        orig = (dt.date.fromisoformat(d) - dt.timedelta(days=offset)).isoformat()
        dest_wp = core.find_wp(v, p["to"])
        rows.append({"date": d, "i": i, "rest": bool(p.get("rest")), "night": bool(p.get("night")),
                     "frm": core.find_wp(v, p["from"])["name"],
                     "to": dest_wp["name"], "to_id": dest_wp["id"],
                     "rating": dest_wp.get("rating"), "photo": photo_ref(dest_wp, offline),
                     "nm": round(tot, 1), "tappe": tappe, "n_tappe": len(tappe),
                     "verify": any(t["verify"] for t in tappe),
                     "tier": confidence_tier(i),
                     "crew_delta": {"on": [m["name"] for m in v["crew"] if m["board"] == orig],
                                    "off": [m["name"] for m in v["crew"] if m["leave"] == orig]},
                     "wx": None, "wave": None, "_dest": dest_wp})

    wx_rows = [r for r in rows if r["tier"] != "programma"]
    if offline:
        for r in wx_rows:
            r["wx"] = {"wmo": 1, "tmax": 29, "tmin": 22, "rain_prob": 5,
                       "wind_max": 16, "gust_max": 22, "wind_dir": 305, "synthetic": True}
            if r["i"] <= 7:
                r["wave"] = {"hmax": 0.6, "dir": 290, "period": 4.2, "synthetic": True}
    elif wx_rows:
        try:
            resp = weather.daily_at([(r["_dest"]["lat"], r["_dest"]["lon"]) for r in wx_rows],
                                    wx_rows[0]["date"], wx_rows[-1]["date"])
            for r, met in zip(wx_rows, resp):
                try:
                    dd = met["daily"]
                    j = dd["time"].index(r["date"])
                    r["wx"] = {"wmo": dd["weather_code"][j], "tmax": dd["temperature_2m_max"][j],
                               "tmin": dd["temperature_2m_min"][j],
                               "rain_prob": dd["precipitation_probability_max"][j],
                               "wind_max": dd["wind_speed_10m_max"][j],
                               "gust_max": dd["wind_gusts_10m_max"][j],
                               "wind_dir": dd["wind_direction_10m_dominant"][j]}
                except Exception:
                    pass
        except Exception:
            pass
        sea_rows = [r for r in wx_rows if r["i"] <= 7]
        if sea_rows:
            try:
                resp = weather.sea_daily([(r["_dest"]["lat"], r["_dest"]["lon"]) for r in sea_rows],
                                         sea_rows[0]["date"], sea_rows[-1]["date"])
                for r, met in zip(sea_rows, resp):
                    try:
                        dd = met["daily"]
                        j = dd["time"].index(r["date"])
                        r["wave"] = {"hmax": dd["wave_height_max"][j],
                                     "dir": dd["wave_direction_dominant"][j],
                                     "period": dd["wave_period_max"][j]}
                    except Exception:
                        pass
            except Exception:
                pass

    for r in rows:
        r.pop("_dest")
        r.pop("i")

    # catalogo destinazioni: tutti i waypoint votati, ordinati per voto.
    # Il voto e' una STIMA (bozza da guide): si conferma a bordo.
    dests = sorted(
        ({"id": w["id"], "name": w["name"], "type": w.get("type"),
          "rating": w["rating"], "notes": w.get("notes"),
          "verify": bool(w.get("verify")), "coords": [w["lat"], w["lon"]],
          "photo": photo_ref(w, offline)}
         for w in v["waypoints"] if w.get("rating") is not None),
        key=lambda d: -d["rating"])

    return {"generated_at": now, "sim": bool(offset), "day": day,
            "start_date": plan_all[0]["date"] if plan_all else None,
            "end_date": plan_all[-1]["date"] if plan_all else None,
            "tiers": TIER_LEGEND, "days": rows, "destinations": dests}


def build_destinations(v: dict, now: str) -> dict:
    """Schede dettaglio: join SENZA rete di data/destinations.json (gallery +
    Wikipedia, arricchito a mano con enrich_destinations.py) con i dati vivi —
    voto/note/tipo da voyage.json, riparo da anchorages.json. Se il file manca
    o una voce non c'e', la scheda resta essenziale (la UI degrada)."""
    try:
        src = json.loads((core.DATA / "destinations.json").read_text(encoding="utf-8"))
        enrich = src.get("entries", {})
    except Exception:
        enrich = {}
    shelters = {a["id"]: a for a in core.anchorages()}

    out = {}
    for w in v["waypoints"]:
        if w.get("rating") is None:
            continue
        e = enrich.get(w["id"], {})
        sh = shelters.get(w["id"])
        out[w["id"]] = {
            "name": w["name"], "type": w.get("type"), "rating": w["rating"],
            "verify": bool(w.get("verify")), "notes": w.get("notes"),
            "coords": [w["lat"], w["lon"]],
            "shelter": ({"holding": sh.get("holding"), "depth_m": sh.get("depth_m"),
                         "exposed_from": sh.get("exposed_from"),
                         "exposed_to": sh.get("exposed_to")} if sh else None),
            "gallery": e.get("gallery", []),
            "wiki": e.get("wiki"),
        }
    return {"generated_at": now, "entries": out}


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


DUTIES_ALL = ["cucina", "pulizie", "check"]


def day_turns(crew: list[dict], day_idx: int) -> dict:
    """6 turni/giorno assegnati per POOL di ruolo: ogni membro ha in `duties`
    cosa sa/puo' fare (default: tutto tranne gli skipper, che sono esenti).
    Ogni pool ruota indipendentemente, 2 slot al giorno."""
    def pool(duty):
        return [m["name"] for m in crew
                if m["role"] != "skipper" and duty in m.get("duties", DUTIES_ALL)]
    out = {}
    for di, (duty, slots) in enumerate((("cucina", ["cucina_pranzo", "cucina_cena"]),
                                        ("pulizie", ["pulizie_pranzo", "pulizie_cena"]),
                                        ("check", ["check_mattina", "check_pomeriggio"]))):
        p = pool(duty)
        for j, slot in enumerate(slots):
            # offset per ruolo (di*2): con pool uguali i 6 slot si spalmano su
            # persone diverse; avanzamento di 1 al giorno cosi' ruota anche con
            # pool piccoli (es. 2 soli cuochi si alternano davvero)
            out[slot] = p[(day_idx + di * 2 + j) % len(p)] if p else None
    return out


def live_position() -> dict | None:
    """Posizione reale da data/position.json (scritta dal workflow via telefono).
    Vale 24 ore: piu' vecchia di cosi', meglio la posizione da piano che una bugia."""
    try:
        p = json.loads((core.DATA / "position.json").read_text(encoding="utf-8"))
        at = dt.datetime.fromisoformat(p["at"].replace("Z", "+00:00"))
        age_h = (dt.datetime.now(dt.timezone.utc) - at).total_seconds() / 3600
        if 0 <= age_h <= 24:
            return {"lat": float(p["lat"]), "lon": float(p["lon"]),
                    "name": p.get("name") or "posizione GPS",
                    "at": p["at"], "age_h": round(age_h, 1), "live": True}
    except Exception:
        pass
    return None


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
        row = {"date": r["date"], "rest": p["rest"], "night": bool(p.get("night")),
               "frm": a["name"], "to": b["name"], "to_id": b["id"], "nm": round(nm, 1),
               "n_tappe": len(norm_steps(p)),
               "rating": b.get("rating"), "photo": photo_ref(b, offline)}
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
    # posizione reale (telefono -> workflow) batte quella derivata dal piano
    pos = live_position()
    if pos:
        wp = {**wp, "lat": pos["lat"], "lon": pos["lon"], "name": pos["name"]}

    if offline:
        series = synth(day)
        conf = {"confidence": "n/d (offline)", "mean_spread_kn": None}
    else:
        series = weather.combined(wp["lat"], wp["lon"], days=4)
        try:
            conf = weather.ensemble_spread(wp["lat"], wp["lon"])
        except Exception as e:
            conf = {"confidence": "sconosciuta", "error": str(e)}

    # ---- tappe del giorno (fino a 3: rada mattina / pomeriggio / sera)
    steps = build_day_steps(v, plan, day, series, offline) if plan else []

    # ---- tratta di oggi
    leg, options, stop_reason = None, [], None
    if plan and not plan["rest"] and plan.get("night"):
        # NOTTURNA: si salpa in serata, si arriva all'alba. Gate non negoziabile:
        # mare piatto lungo il transito, altrimenti si consiglia il piano diurno.
        w0, w1 = v["preferences"].get("night_departure_window", ["20:00", "23:00"])
        for h in range(int(w0[:2]), int(w1[:2]) + 1):
            depart = f"{day}T{h:02d}:00"
            try:
                r = routing.simulate_leg(v, plan["from"], plan["to"], depart, series)
            except ValueError:
                continue
            if not r.get("abort"):
                options.append(r)
        options = sorted(options, key=lambda x: x["avg_score"], reverse=True)[:3]
        leg = options[0] if options else None
        if leg:
            leg["night"] = True
            i0 = next((i for i, r in enumerate(series) if r["time"] >= leg["depart"]), 0)
            transit = series[i0:i0 + max(1, int(leg["hours"]) + 1)]
            wmax = max((r.get("wave") if r.get("wave") is not None else 0) for r in transit)
            thr = v["preferences"].get("night_max_wave_m", 0.5)
            leg["night_check"] = {"ok": wmax <= thr, "max_wave": round(wmax, 2),
                                  "max_tws": round(max(r["tws"] for r in transit), 1), "thr": thr}
    elif plan and not plan["rest"] and plan.get("steps"):
        # giorno a tappe esplicite: la tratta "principale" del briefing e' la
        # piu' lunga (per le notturne coincide col passaggio: gate invariato)
        moves = [s for s in steps if not s["stay"] and not s.get("abort") and s.get("eta")]
        leg = max(moves, key=lambda s: s["nm"]) if moves else None
        if leg is None:
            ab = next((s for s in steps if s.get("abort") and s.get("reason")), None)
            stop_reason = ("STOP: " + ab["reason"]) if ab else None
    elif plan and not plan["rest"]:
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

    def enrich_rada(r: dict) -> dict:
        # voto (STIMA in voyage.json) e foto Commons della rada
        try:
            w = core.find_wp(v, r["id"])
        except KeyError:
            return r
        return {**r, "rating": w.get("rating"), "photo": photo_ref(w, offline)}
    ranked = [enrich_rada(r) for r in ranked]
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
        "departure_at": v.get("departure_at"),
        "position": {"id": wp["id"], "name": wp["name"], "lat": wp["lat"], "lon": wp["lon"],
                     "live": bool(pos), "age_h": pos["age_h"] if pos else None},
        "rest": bool(plan and plan["rest"]),
        "leg": leg, "leg_sailing": leg_sailing, "options": options, "confidence": conf,
        "steps": steps,
        "day_nm": round(sum(s["nm"] for s in steps), 1) if steps else None,
        "stop_reason": stop_reason or (options[0].get("note") if options and leg is None else None),
        "tonight": tonight, "plan_b": plan_b, "ranked": ranked[:4],
        "outlook": outlook,
        "polar_estimated": v["boat"].get("polar_status", "stimata") == "stimata",
        "crew": [{"name": m["name"], "role": m["role"], "board": m["board"],
                  "leave": m["leave"], "cabin": m.get("cabin")} for m in crew],
        "turns": day_turns(crew, (dt.date.fromisoformat(day) - dt.date.fromisoformat(plan_all[0]["date"])).days
                           if plan_all else 0),
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
    program = build_program(v, plan_all, day, offset, offline, now)
    return briefing, wx, conti, program


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

    briefing, wx, conti, program = build(a.day, a.offline)
    # schede dettaglio: join senza rete del file arricchito a mano (mai fetch qui)
    dests = build_destinations(core.load(), briefing["generated_at"])
    for name, obj in (("briefing", briefing), ("weather", wx), ("conti", conti),
                      ("program", program), ("destinations", dests)):
        (SITE / f"{name}.json").write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    tag = briefing["leg"]["leg"] if briefing["leg"] else ("sosta" if briefing["rest"] else "—")
    print(f"Pubblicato {a.day}: {tag} | score {briefing['leg']['avg_score'] if briefing['leg'] else '—'} "
          f"| rada {briefing['tonight']['name'] if briefing['tonight'] else '—'} "
          f"({briefing['tonight']['light'] if briefing['tonight'] else '?'})")
