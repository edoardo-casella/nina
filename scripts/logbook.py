"""Diario di bordo. Due livelli:
  - dati duri: miglia, rotta, vento reale, ancoraggio, motore
  - racconto: due righe di narrativa, quelle che fra dieci anni valgono di piu'

`add` registra una giornata, `render` produce il diario in markdown.
"""
from __future__ import annotations
import argparse, datetime as dt
from core import load, save, aboard_on


def add(v: dict, **kw) -> dict:
    entry = {
        "date": kw["date"],
        "from": kw.get("frm"), "to": kw.get("to"),
        "nm": kw.get("nm"), "engine_hours": kw.get("engine_hours", 0),
        "wind": kw.get("wind"),          # es. "NW 18 kn, raffiche 24"
        "sea": kw.get("sea"),            # es. "onda 0.8 m"
        "anchorage": kw.get("anchorage"),
        "crew_aboard": [m["name"] for m in aboard_on(v, kw["date"])],
        "highlight": kw.get("highlight"),
        "notes": kw.get("notes"),
        "sail_score": kw.get("sail_score"),
    }
    v["logbook"] = [e for e in v["logbook"] if e["date"] != entry["date"]] + [entry]
    v["logbook"].sort(key=lambda e: e["date"])
    return entry


def totals(v: dict) -> dict:
    nm = sum(e.get("nm") or 0 for e in v["logbook"])
    eng = sum(e.get("engine_hours") or 0 for e in v["logbook"])
    return {"days": len(v["logbook"]), "nm": round(nm, 1), "engine_hours": round(eng, 1),
            "anchorages": len({e["anchorage"] for e in v["logbook"] if e.get("anchorage")})}


def render(v: dict) -> str:
    t = totals(v)
    out = [f"# Diario di bordo — {v['name']}",
           f"*{v['boat']['name']}, {v['boat']['model']}*", "",
           f"**{t['days']} giorni · {t['nm']} nm · {t['engine_hours']} h di motore · {t['anchorages']} rade**", ""]
    for e in v["logbook"]:
        d = dt.date.fromisoformat(e["date"]).strftime("%d %B %Y")
        out.append(f"## {d}")
        if e.get("from") and e.get("to"):
            out.append(f"**{e['from']} → {e['to']}** — {e.get('nm','?')} nm")
        if e.get("wind"):
            out.append(f"Vento: {e['wind']}. Mare: {e.get('sea','—')}.")
        if e.get("anchorage"):
            out.append(f"Ancoraggio: {e['anchorage']}.")
        if e.get("crew_aboard"):
            out.append(f"A bordo: {', '.join(e['crew_aboard'])}.")
        if e.get("highlight"):
            out.append(f"\n> {e['highlight']}")
        if e.get("notes"):
            out.append(f"\n{e['notes']}")
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--date", required=True)
    for f in ("frm", "to", "wind", "sea", "anchorage", "highlight", "notes"):
        a.add_argument(f"--{f}")
    a.add_argument("--nm", type=float); a.add_argument("--engine-hours", type=float, default=0)
    a.add_argument("--sail-score", type=int)
    sub.add_parser("render")
    sub.add_parser("totals")
    args = ap.parse_args()

    v = load()
    if args.cmd == "add":
        e = add(v, **{k: getattr(args, k) for k in vars(args) if k != "cmd"})
        save(v)
        print(f"Registrato {e['date']}: {e.get('from')} -> {e.get('to')}")
    elif args.cmd == "render":
        print(render(v))
    else:
        print(totals(v))
