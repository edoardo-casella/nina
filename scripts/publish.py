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
                    "wave": round(0.2 + tws / 30, 2), "rain": 0})
    return out


def leg_for(v: dict, day: str) -> dict | None:
    return next((p for p in v["plan"] if p["date"] == day), None)


def build(day: str, offline: bool) -> tuple[dict, dict, dict]:
    v = core.load()
    plan = leg_for(v, day)
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
            leg = options[0] if options else None
        finally:
            weather.combined = _real

    # ---- rada di stanotte
    night = next((r for r in series if r["time"].startswith(day) and r["time"][11:] == "21:00"), series[min(21, len(series) - 1)])
    dest = plan["to"] if plan else start_id
    ranked = shelter.rank(night["twd"], night["tws"], night.get("gust", night["tws"] * 1.3))
    tonight = next((r for r in ranked if r["id"] == dest), None)
    plan_b = next((r for r in ranked if r["id"] != dest and r["light"] == "verde"), None)

    # ---- outlook 3 giorni
    outlook = []
    for i in range(1, 4):
        d = (dt.date.fromisoformat(day) + dt.timedelta(days=i)).isoformat()
        p = leg_for(v, d)
        day_hours = [r for r in series if r["time"].startswith(d)]
        if not (p and day_hours):
            continue
        if p["rest"]:
            outlook.append({"date": d, "leg": "sosta", "score": None, "light": "verde"})
            continue
        a, b = core.find_wp(v, p["from"]), core.find_wp(v, p["to"])
        cog = core.bearing((a["lat"], a["lon"]), (b["lat"], b["lon"]))
        pol = core.polar(v)
        best = max(day_hours, key=lambda r: routing.sail_score(
            core.twa(r["twd"], cog), r["tws"], r.get("gust", r["tws"]), r.get("wave", .3), v["boat"], pol)["score"])
        s = routing.sail_score(core.twa(best["twd"], cog), best["tws"], best.get("gust", best["tws"]),
                               best.get("wave", .3), v["boat"], pol)
        outlook.append({"date": d, "leg": f"{a['name']} → {b['name']}", "score": s["score"],
                        "light": LIGHTS[s["verdict"]], "verdict": s["verdict"]})

    crew = core.aboard_on(v, day)
    now = dt.datetime.now().isoformat(timespec="minutes")

    briefing = {
        "generated_at": now, "approved": False, "approved_by": None,
        "day": day, "boat": v["boat"]["name"], "voyage": v["name"],
        "rest": bool(plan and plan["rest"]),
        "leg": leg, "options": options, "confidence": conf,
        "tonight": tonight, "plan_b": plan_b, "ranked": ranked[:4],
        "outlook": outlook,
        "crew": [{"name": m["name"], "role": m["role"]} for m in crew],
        "turns": {"cambusa": crew[len(crew) // 2]["name"] if crew else None,
                  "cucina": crew[0]["name"] if crew else None,
                  "tender": crew[-1]["name"] if crew else None},
        "source": "Open-Meteo (ECMWF) — non ufficiale",
        "official": "https://www.meteoam.it/it/mare",
    }
    wx = {"generated_at": now, "waypoint": wp["name"], "hours": series[:48]}
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
