"""Cambusa: genera la lista della spesa per un intervallo, scalata sulle persone
effettivamente a bordo giorno per giorno, e tiene conto delle diete.

Consumi in unita' per PERSONA-GIORNO. Modificare RATES a piacere.
Regola pratica: acqua 3 L/persona/giorno anche col dissalatore (guasti capitano).
"""
from __future__ import annotations
import argparse, datetime as dt, math
from collections import defaultdict
from core import load, aboard_on, parse_date

RATES = {
    "Acqua in bottiglia (L)": 1.5,
    "Pasta / riso (g)": 120,
    "Pane (g)": 100,
    "Verdura fresca (g)": 250,
    "Frutta (g)": 250,
    "Carne / pesce (g)": 150,
    "Uova (n)": 0.5,
    "Formaggio (g)": 60,
    "Latte (ml)": 150,
    "Caffe' (dosi)": 2,
    "Birra (n)": 1.0,
    "Vino (bottiglie)": 0.25,
    "Snack / biscotti (g)": 80,
    "Ghiaccio (kg)": 0.3,
}
# voci da azzerare/sostituire per dieta
DIET_SKIP = {
    "vegetariano": ["Carne / pesce (g)"],
    "vegano": ["Carne / pesce (g)", "Formaggio (g)", "Uova (n)", "Latte (ml)"],
    "no glutine": ["Pane (g)"],
}
SAFETY_MARGIN = 1.10  # 10% in piu': ospiti, sprechi, giornata di calma piatta


def person_days(v: dict, start: str, end: str) -> tuple[int, dict]:
    d0, d1 = parse_date(start), parse_date(end)
    total, by_diet = 0, defaultdict(int)
    d = d0
    while d < d1:
        for m in aboard_on(v, d.isoformat()):
            total += 1
            by_diet[m.get("diet", "onnivoro")] += 1
        d += dt.timedelta(days=1)
    return total, dict(by_diet)


def shopping_list(v: dict, start: str, end: str) -> dict:
    total_pd, by_diet = person_days(v, start, end)
    items = {}
    for item, rate in RATES.items():
        pd = total_pd
        for diet, n in by_diet.items():
            if item in DIET_SKIP.get(diet, []):
                pd -= n
        qty = rate * pd * SAFETY_MARGIN
        items[item] = math.ceil(qty * 10) / 10
    budget = sum(c["eur_per_person_day"] for c in v["costs"]["variable_budget"]
                 if c["label"] == "Cambusa") * total_pd
    return {"person_days": total_pd, "by_diet": by_diet, "items": items, "budget_eur": round(budget)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Lista cambusa per un intervallo")
    ap.add_argument("start"); ap.add_argument("end")
    a = ap.parse_args()
    v = load()
    r = shopping_list(v, a.start, a.end)
    print(f"Tratta {a.start} -> {a.end}  |  {r['person_days']} persona-giorno  |  budget ~{r['budget_eur']} EUR")
    print(f"Diete: {r['by_diet']}\n")
    for k, q in r["items"].items():
        print(f"  {k:<30} {q}")
    print("\nNota: +10% di margine gia' incluso. Acqua: prevedere comunque riserva d'emergenza.")
