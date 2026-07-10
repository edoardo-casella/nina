"""Conti dell'equipaggio con imbarchi e sbarchi scaglionati.

Principio: chi dorme una notte in barca paga una notte. L'unita' di conto e'
la PERSONA-NOTTE. I costi fissi (charter, pulizie, cauzione) si spalmano su
tutte le persona-notte; chi resta 20 notti paga il doppio di chi ne resta 10.
Alcune voci si dividono invece in parti uguali (es. i SUP restano a chi li usa
per tutto il viaggio) -> campo "split": "person_nights" | "equal".
"""
from __future__ import annotations
import argparse, datetime as dt
from collections import defaultdict
from core import load, nights_aboard, aboard_on, parse_date


def days(v: dict) -> list[str]:
    d0, d1 = parse_date(v["start_date"]), parse_date(v["end_date"])
    return [(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days)]


def shares(v: dict) -> dict:
    pn = {m["id"]: nights_aboard(m) for m in v["crew"]}
    total_pn = sum(pn.values())
    n = len(v["crew"])
    out = {m["id"]: {"name": m["name"], "nights": pn[m["id"]], "fixed": 0.0, "variable": 0.0} for m in v["crew"]}

    for c in v["costs"]["fixed"]:
        if c["split"] == "equal":
            for k in out:
                out[k]["fixed"] += c["amount"] / n
        else:
            for k in out:
                out[k]["fixed"] += c["amount"] * pn[k] / total_pn

    per_day = sum(c["eur_per_person_day"] for c in v["costs"]["variable_budget"])
    for k in out:
        out[k]["variable"] = per_day * pn[k]

    for k in out:
        out[k]["total"] = round(out[k]["fixed"] + out[k]["variable"], 2)
        out[k]["fixed"] = round(out[k]["fixed"], 2)
        out[k]["variable"] = round(out[k]["variable"], 2)
    return {"total_person_nights": total_pn, "per_person": out}


def _beneficiaries(v: dict, e: dict) -> list[str]:
    if e["beneficiaries"] == "aboard":
        crew = aboard_on(v, e["date"])
        return [m["id"] for m in crew] or [m["id"] for m in v["crew"]]
    return e["beneficiaries"]


def settle(v: dict) -> dict:
    """Chi ha anticipato cosa -> lista minima di bonifici per pareggiare."""
    paid, owed = defaultdict(float), defaultdict(float)
    for e in v["expenses"]:
        paid[e["paid_by"]] += e["amount"]
        bens = _beneficiaries(v, e)
        for b in bens:
            owed[b] += e["amount"] / len(bens)

    net = {m["id"]: round(paid[m["id"]] - owed[m["id"]], 2) for m in v["crew"]}
    creditors = sorted([(k, x) for k, x in net.items() if x > 0.01], key=lambda t: -t[1])
    debtors = sorted([(k, -x) for k, x in net.items() if x < -0.01], key=lambda t: -t[1])

    transfers, i, j = [], 0, 0
    while i < len(debtors) and j < len(creditors):
        d, dv = debtors[i]; c, cv = creditors[j]
        amt = round(min(dv, cv), 2)
        transfers.append({"from": d, "to": c, "amount": amt})
        debtors[i] = (d, dv - amt); creditors[j] = (c, cv - amt)
        if debtors[i][1] < 0.01: i += 1
        if creditors[j][1] < 0.01: j += 1
    return {"net": net, "transfers": transfers, "total_spent": round(sum(paid.values()), 2)}


def occupancy(v: dict) -> list[tuple[str, int]]:
    return [(d, len(aboard_on(v, d))) for d in days(v)]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["quote", "conguaglio", "occupazione"])
    a = ap.parse_args()
    v = load()

    if a.cmd == "quote":
        s = shares(v)
        print(f"Persona-notte totali: {s['total_person_nights']}\n")
        print(f"{'Nome':<14}{'Notti':>6}{'Fissi':>11}{'Variabili':>12}{'TOTALE':>11}")
        for r in s["per_person"].values():
            print(f"{r['name']:<14}{r['nights']:>6}{r['fixed']:>11.0f}{r['variable']:>12.0f}{r['total']:>11.0f}")
    elif a.cmd == "conguaglio":
        s = settle(v)
        names = {m["id"]: m["name"] for m in v["crew"]}
        print(f"Speso finora: {s['total_spent']:.2f} EUR\n")
        for t in s["transfers"]:
            print(f"  {names[t['from']]:<12} -> {names[t['to']]:<12} {t['amount']:>8.2f} EUR")
        if not s["transfers"]:
            print("  Tutti in pari.")
    else:
        for d, n in occupancy(v):
            print(f"{d}  {'█' * n} {n}")
