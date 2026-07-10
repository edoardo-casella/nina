"""Bozza automatica del piano a 3 tappe (rada mattina / pomeriggio / sera).

Espande ogni giorno di plan[] in voyage.json in fino a 3 tappe, usando i
waypoint esistenti (anchorage/mooring) come rade intermedie lungo il corridoio
della rotta. TUTTO esce con verify:true: le coordinate sono stimate e
haversine NON evita la terraferma — la bozza va rivista dallo skipper su
carta nautica prima di fidarsi.

  python scripts/draft_plan.py            # dry-run: tabella di revisione, non scrive
  python scripts/draft_plan.py --write    # scrive data/voyage.json (poi: git diff)

Il piano lo approva lo skipper, mai l'agente: --write si lancia solo dopo
aver letto il dry-run, e il commit resta manuale. I giorni che hanno gia'
`steps` non vengono toccati.
"""
from __future__ import annotations
import argparse
import core

STOP_H = 1.75          # sosta tipica in una rada intermedia (bagno, pranzo)
INTERMEDIATE_ACT = ["bagno"]


def _h(s: str) -> float:
    return int(s[:2]) + int(s[3:5]) / 60


def hhmm(h: float) -> str:
    m = int(round(h * 60 / 15) * 15)      # quarti d'ora
    m = max(0, min(m, 23 * 60 + 45))
    return f"{m // 60:02d}:{m % 60:02d}"


def _nm(v: dict, a_id: str, b_id: str) -> float:
    a, b = core.find_wp(v, a_id), core.find_wp(v, b_id)
    return core.haversine_nm((a["lat"], a["lon"]), (b["lat"], b["lon"]))


def corridor_candidates(v: dict, frm: str, to: str) -> tuple[float, list[dict]]:
    """Rade candidabili come tappa intermedia: deviazione contenuta rispetto
    alla rotta diretta. `frac` = posizione frazionaria lungo la rotta."""
    a, b = core.find_wp(v, frm), core.find_wp(v, to)
    direct = core.haversine_nm((a["lat"], a["lon"]), (b["lat"], b["lon"]))
    out = []
    for w in v["waypoints"]:
        if w["id"] in (frm, to) or w.get("type") not in ("anchorage", "mooring"):
            continue
        d1 = core.haversine_nm((a["lat"], a["lon"]), (w["lat"], w["lon"]))
        d2 = core.haversine_nm((w["lat"], w["lon"]), (b["lat"], b["lon"]))
        # una tappa attaccata alla partenza o all'arrivo non e' una tappa
        if d1 < 1.0 or d2 < 1.0:
            continue
        if d1 + d2 - direct <= max(3.0, 0.25 * direct):
            out.append({"wp": w, "d1": d1, "d2": d2, "frac": d1 / max(d1 + d2, 0.1)})
    return direct, sorted(out, key=lambda c: c["frac"])


def pick_stops(cands: list[dict], n: int, min_sep_nm: float = 2.0) -> list[dict]:
    """Le rade piu' vicine a 1/3 e 2/3 della rotta (o a meta', se una sola),
    tenendole ad almeno `min_sep_nm` l'una dall'altra."""
    if not cands or n <= 0:
        return []
    targets = [0.5] if n == 1 else [1 / 3, 2 / 3]
    picked = []
    for t in targets[:n]:
        pool = [c for c in cands if c not in picked and all(
            core.haversine_nm((c["wp"]["lat"], c["wp"]["lon"]),
                              (q["wp"]["lat"], q["wp"]["lon"])) >= min_sep_nm
            for q in picked)]
        best = min(pool, key=lambda c: abs(c["frac"] - t), default=None)
        if best:
            picked.append(best)
    return sorted(picked, key=lambda c: c["frac"])


def draft_day(v: dict, p: dict, prefs: dict, warns: list[str]) -> list[dict]:
    date = p["date"]
    if p.get("rest"):
        return [{"slot": "giornata", "from": p["from"], "to": p["to"],
                 "activity": ["bordo", "porto"], "night_stay": True, "verify": True}]
    if p.get("night"):
        # notturna: mattina in rada alla partenza, passaggio in serata.
        # Il day-level `night` resta com'e': il gate mare piatto vive li'.
        w0 = prefs.get("night_departure_window", ["20:00", "23:00"])[0]
        return [{"slot": "mattina", "from": p["from"], "to": p["from"],
                 "activity": ["bagno"], "night_stay": False, "verify": True},
                {"slot": "sera", "from": p["from"], "to": p["to"], "depart_at": w0,
                 "activity": [], "night_stay": False, "verify": True}]

    direct, cands = corridor_candidates(v, p["from"], p["to"])
    speed = v["boat"].get("cruise_motor_kn", 7.0)
    t0 = _h(prefs.get("earliest_departure", "08:00"))
    t_max = _h(prefs.get("latest_anchor_time", "17:30"))
    max_nm = prefs.get("max_daily_nm", 30)

    # tratte gia' lunghe: niente giri turistici in mezzo
    want = 0 if direct >= 0.75 * max_nm else min(2, int(prefs.get("swim_stops_per_day", 2)))
    stops = pick_stops(cands, want)
    while stops:
        ids = [p["from"]] + [s["wp"]["id"] for s in stops] + [p["to"]]
        total = sum(_nm(v, ids[i], ids[i + 1]) for i in range(len(ids) - 1))
        if total <= max(max_nm, direct + 4) and total / speed + STOP_H * len(stops) <= t_max - t0:
            break
        stops = stops[:-1]      # degrada a 2 o 1 tappe: mai forzare il budget

    ids = [p["from"]] + [s["wp"]["id"] for s in stops] + [p["to"]]
    n = len(ids) - 1
    slots = {1: ["giornata"], 2: ["mattina", "sera"], 3: ["mattina", "pomeriggio", "sera"]}[n]
    steps, t = [], t0
    for i in range(n):
        nm = _nm(v, ids[i], ids[i + 1])
        last = i == n - 1
        # pattern dello skipper: prima rada raggiunta presto (poco affollata),
        # ultima tratta calcolata ALL'INDIETRO per arrivare al limite serale
        depart = max(t, t_max - nm / speed) if (last and n > 1) else t
        arrive = depart + nm / speed
        if last and arrive > t_max:
            warns.append(f"{date}: arrivo stimato {hhmm(arrive)} oltre latest_anchor_time "
                         f"({prefs.get('latest_anchor_time')}) — tappe ridotte o partenza anticipata da valutare")
        steps.append({"slot": slots[i], "from": ids[i], "to": ids[i + 1],
                      "depart_at": hhmm(depart), "arrive_by": hhmm(min(arrive, t_max) if last else arrive),
                      "activity": [] if last else list(INTERMEDIATE_ACT),
                      "night_stay": last, "verify": True})
        t = arrive + (0 if last else STOP_H)
    return steps


def validate(v: dict) -> list[str]:
    errs = []
    prefs = v.get("preferences", {})
    max_nm = prefs.get("max_daily_nm", 30)
    for p in v["plan"]:
        steps = p.get("steps")
        if not steps:
            continue
        d = p["date"]
        if steps[0]["from"] != p["from"]:
            errs.append(f"{d}: steps[0].from ({steps[0]['from']}) != day.from ({p['from']})")
        if steps[-1]["to"] != p["to"]:
            errs.append(f"{d}: steps[-1].to ({steps[-1]['to']}) != day.to ({p['to']})")
        for s1, s2 in zip(steps, steps[1:]):
            if s1["to"] != s2["from"]:
                errs.append(f"{d}: catena spezzata {s1['to']} -> {s2['from']}")
        total = 0.0
        for s in steps:
            try:
                total += _nm(v, s["from"], s["to"])
            except KeyError as e:
                errs.append(f"{d}: waypoint non risolvibile {e}")
        try:
            cap = max(max_nm, _nm(v, p["from"], p["to"]) + 4)
            if total > cap + 0.1:
                errs.append(f"{d}: {total:.1f} nm oltre il tetto {cap:.1f}")
        except KeyError:
            pass
        nights = sum(1 for s in steps if s.get("night_stay"))
        if p.get("night"):
            if nights:
                errs.append(f"{d}: notturna ma night_stay={nights} (si dorme in navigazione)")
        elif nights != 1:
            errs.append(f"{d}: night_stay deve essere esattamente 1 (trovati {nights})")
    return errs


def main() -> None:
    ap = argparse.ArgumentParser(description="Bozza del piano a 3 tappe (dry-run di default)")
    ap.add_argument("--write", action="store_true", help="scrive data/voyage.json")
    a = ap.parse_args()

    v = core.load()
    prefs = v.get("preferences", {})
    warns: list[str] = []
    drafted = skipped = 0

    print(f"{'data':<12}{'tratta':<42}{'tappe':>6}{'nm':>8}")
    print("-" * 68)
    for p in v["plan"]:
        if p.get("steps"):
            skipped += 1
            print(f"{p['date']:<12}{p['from']} -> {p['to']:<30}   gia' con tappe: non tocco")
            continue
        steps = draft_day(v, p, prefs, warns)
        p["steps"] = steps
        drafted += 1
        total = sum(_nm(v, s["from"], s["to"]) for s in steps)
        print(f"{p['date']:<12}{(p['from'] + ' -> ' + p['to']):<42}{len(steps):>6}{total:>8.1f}")
        for s in steps:
            frm, to = core.find_wp(v, s["from"])["name"], core.find_wp(v, s["to"])["name"]
            leg = f"{frm} -> {to}" if s["from"] != s["to"] else f"{frm} (sosta)"
            times = f"{s.get('depart_at', '—')} -> {s.get('arrive_by', '—')}" if s["from"] != s["to"] else ""
            act = ",".join(s["activity"]) or "-"
            moon = " [notte]" if s["night_stay"] else ""
            print(f"  {s['slot']:<11} {leg:<44} {times:<15} {act}{moon}")

    errs = validate(v)
    print("-" * 68)
    print(f"{drafted} giorni bozzati, {skipped} gia' con tappe.")
    if warns:
        print("\nAVVISI (decide lo skipper):")
        for w in warns:
            print("  ⚠ " + w)
    print(f"\nNOTA: gli arrivi serali sono clippati a latest_anchor_time="
          f"{prefs.get('latest_anchor_time')} (ordine permanente in voyage.json). "
          "Se vuoi il pattern 'arrivo in rada 18-19', alza la preferenza e rilancia.")
    if errs:
        print("\nERRORI di validazione (blocco la scrittura):")
        for e in errs:
            print("  ✗ " + e)
        raise SystemExit(1)

    if a.write:
        core.save(v)
        print("\nScritto data/voyage.json — rivedi con `git diff data/voyage.json` "
              "prima di committare. Tutte le tappe sono verify:true.")
    else:
        print("\nDRY-RUN: niente scritto. Rilancia con --write dopo la revisione.")


if __name__ == "__main__":
    main()
