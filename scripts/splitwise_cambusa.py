"""Riparto cambusa Nina I + scorporo alcolici + cessione dispensa a Nina II.

One-off del cambio equipaggio 15/08/2026, concordato con Edo. Le due ricevute
Dettori (1300 Bernardo + 355 Edo, id 4628343978/4628335186 circa) restano in
app a saldo zero ("solo pagatore") come pezze giustificative: qui si creano le
spese che muovono i saldi:

  E1 Nina I  "Cambusa comune"        923.90 = 1655 - 302.07 - 429.03, 11 quote
  E2 Nina I  "Cambusa - alcolici"    302.07, 10 quote (esclusa Valentina F)
  E3 Nina I  "Cessione a Nina II"    429.03, a carico di Edo (la recupera in II)
  E4 Nina II "Acquisto da Nina I"    429.03, per ora solo Edo (placeholder:
             ripartire sull'equipaggio quando entra nel gruppo)

Spesa John Barrille (definitiva 15/8 sera, per BATCH — supera le percentuali
55/45 delle prime due stesure): 800 totali anticipati Edo 550 + Giacomo 250.
Batch: 10x25=250 (ricevuta Edo, FINITO da Nina I) + 20x15=300 (ricevuta Edo,
consumato il 15%=45, l'85%=255 venduto a Nina II) + batch di Giacomo da 250
(FINITO da Nina I). Quindi consumo Nina I = 250+45+250 = 545, diviso per
COEFFICIENTI (Vale 10, Giacomo 5.5, Gine 3, Edo 4); cessione a Nina II = 255:

  E5 Nina I  "John Barrille - consumo"   545.00, quote da coefficienti
  E6 Nina I  "Cessione JB a Nina II"     255.00, a carico di Edo
  E7 Nina II "Acquisto JB da Nina I"     255.00, placeholder solo Edo

Se una spesa marcata esiste gia' ma con costo diverso dal piano, lo script la
AGGIORNA (update_expense) invece di saltarla: correzioni idempotenti.
  + la ricevuta originale "John Barrille" 550 viene aggiornata a 800 con i due
    pagatori veri (resta a saldo zero, solo documentale)

Crediti degli anticipatori (Bernardo/Edo) spalmati su E1-E3 pro-rata
dell'anticipo, con aggiustamento centesimi su E3: gli assert garantiscono che
i totali tornino ESATTI (Bernardo 1300.00, Edo 355.00, ogni spesa quadrata).

Uso:  python scripts/splitwise_cambusa.py            # dry-run
      python scripts/splitwise_cambusa.py --write    # crea le 4 spese
Env:  SPLITWISE_API_KEY. Idempotente via marker [nina-cambusa:<slug>].
"""
from __future__ import annotations
import os, re, sys

from splitwise import NAME_MAP, expenses
from splitwise_extras import _post

NINA1, NINA2 = 101493357, 101863026
EDO, BERNARDO, VALENTINA = 20136237, 35630477, 104408857
DATE = "2026-08-15"

T = 1655.00           # Spesa Dettori 1300 (Bernardo) + Market Dettori Primo 355 (Edo)
ALCOL = 302.07        # alcolici del primo gruppo (fuori Valentina)
CESSIONE = 429.03     # dispensa avanzata che Nina II compra da Nina I
FRONTED = {BERNARDO: 1300.00, EDO: 355.00}

GIACOMO, VALE, GINE = 35409668, 104408857, 31837892
JB_T = 800.00                                  # spesa John Barrille totale
JB_FRONTED = {EDO: 550.00, GIACOMO: 250.00}
JB_CONSUMO = 545.00                            # 250 + 45 (15% di 300) + 250 (batch Giacomo)
JB_CESSIONE = round(JB_T - JB_CONSUMO, 2)      # 255.00 = 85% del batch 20x15, a Nina II
JB_COEFF = {VALE: 10, GIACOMO: 5.5, GINE: 3.5, EDO: 3.5}   # 22.5 punti; Edo e
# Gine parificati (decisione 15/8 sera): la loro somma resta 7, Vale e Jack invariati

MEMBERS = sorted(NAME_MAP)          # gli 11 di Nina I (NAME_MAP e' esattamente quel gruppo)
BEVITORI = [u for u in MEMBERS if u != VALENTINA]


def equal_shares(cost: float, uids: list[int]) -> dict[int, float]:
    """Quote eque al centesimo, resti distribuiti dai primi uid (largest remainder)."""
    base = int(cost * 100) // len(uids)
    cents = [base] * len(uids)
    for i in range(int(round(cost * 100)) - base * len(uids)):
        cents[i] += 1
    return {u: c / 100 for u, c in zip(uids, cents)}


def weighted_shares(cost: float, weights: dict[int, float]) -> dict[int, float]:
    """Quote proporzionali ai pesi, quadrate al centesimo (largest remainder)."""
    tot_c, tot_w = int(round(cost * 100)), sum(weights.values())
    raw = {u: tot_c * w / tot_w for u, w in weights.items()}
    cents = {u: int(r) for u, r in raw.items()}
    for u in sorted(raw, key=lambda u: raw[u] - cents[u], reverse=True)[:tot_c - sum(cents.values())]:
        cents[u] += 1
    return {u: c / 100 for u, c in cents.items()}


def prorata(cost: float, fronted: dict[int, float] | None = None,
            total: float | None = None) -> dict[int, float]:
    """Crediti anticipatori pro-rata; il resto centesimale all'ultimo (Edo)."""
    fronted, total = fronted or FRONTED, total or T
    uids = sorted(fronted, key=lambda u: u == EDO)   # Edo per ultimo
    out = {u: round(cost * fronted[u] / total, 2) for u in uids[:-1]}
    out[uids[-1]] = round(cost - sum(out.values()), 2)
    return out


def build() -> list[dict]:
    e1p, e2p = prorata(923.90), prorata(ALCOL)
    # E3 chiude i conti: a ciascun anticipatore il residuo esatto dell'anticipo
    e3p = {u: round(FRONTED[u] - e1p[u] - e2p[u], 2) for u in FRONTED}
    plans = [
        {"group": NINA1, "slug": "dispensa", "desc": "Cambusa comune (Dettori)",
         "cost": 923.90, "paid": e1p, "owed": equal_shares(923.90, MEMBERS),
         "note": "Spese Dettori 1655.00 al netto di 302.07 alcolici e 429.03 di dispensa ceduta a Nina II. Le ricevute Dettori originali restano a saldo zero."},
        {"group": NINA1, "slug": "alcolici", "desc": "Cambusa · alcolici",
         "cost": ALCOL, "paid": e2p, "owed": equal_shares(ALCOL, BEVITORI),
         "note": "Alcolici delle spese Dettori, divisi fra chi beve (esclusa Valentina)."},
        {"group": NINA1, "slug": "storno", "desc": "Cessione cambusa a Nina II (storno)",
         "cost": CESSIONE, "paid": e3p, "owed": {EDO: CESSIONE},
         "note": "Dispensa avanzata venduta all'equipaggio di Nina II: il valore torna ai partecipanti di Nina I; Edo lo incassa dal gruppo Nina II."},
        {"group": NINA2, "slug": "acquisto", "desc": "Acquisto cambusa da Nina I",
         "cost": CESSIONE, "paid": {EDO: CESSIONE}, "owed": {EDO: CESSIONE},
         "note": "Dispensa comprata dall'equipaggio di Nina I. Placeholder intestato a Edo: da ripartire sull'equipaggio quando entra nel gruppo."},
    ]
    # --- John Barrille: consumo per coefficienti + cessione invenduto ---
    jb_owed = weighted_shares(JB_CONSUMO, JB_COEFF)
    jb1p = prorata(JB_CONSUMO, JB_FRONTED, JB_T)
    jb2p = {u: round(JB_FRONTED[u] - jb1p[u], 2) for u in JB_FRONTED}
    plans += [
        {"group": NINA1, "slug": "jb_consumo", "desc": "John Barrille · consumo Nina I",
         "cost": JB_CONSUMO, "paid": jb1p, "owed": jb_owed,
         "note": "Quanto consumato da Nina I degli 800 di John Barrille (545: batch 10x25 intero + 15% del batch 20x15 + batch di Giacomo da 250), diviso per coefficienti di consumo (Vale 10, Giacomo 5.5, Gine 3, Edo 4)."},
        {"group": NINA1, "slug": "jb_storno", "desc": "Cessione John Barrille a Nina II (storno)",
         "cost": JB_CESSIONE, "paid": jb2p, "owed": {EDO: JB_CESSIONE},
         "note": "L'invenduto di John Barrille (255 = 85% del batch 20x15) passa all'equipaggio di Nina II: il valore torna agli anticipatori (Edo 550, Giacomo 250); Edo lo incassa dal gruppo Nina II."},
        {"group": NINA2, "slug": "jb_acquisto", "desc": "Acquisto John Barrille da Nina I",
         "cost": JB_CESSIONE, "paid": {EDO: JB_CESSIONE}, "owed": {EDO: JB_CESSIONE},
         "note": "Invenduto John Barrille comprato dall'equipaggio di Nina I. Placeholder intestato a Edo: da ripartire sull'equipaggio quando entra nel gruppo."},
    ]
    # invarianti contabili: ogni spesa quadrata, anticipi restituiti al centesimo
    for p in plans:
        assert round(sum(p["paid"].values()), 2) == p["cost"], p["slug"]
        assert round(sum(p["owed"].values()), 2) == p["cost"], p["slug"]
    for u, tot in FRONTED.items():
        assert round(e1p[u] + e2p[u] + e3p[u], 2) == tot, f"anticipo {u}"
    for u, tot in JB_FRONTED.items():
        assert round(jb1p[u] + jb2p[u], 2) == tot, f"anticipo JB {u}"
    assert VALENTINA not in plans[1]["owed"]
    assert round(sum(jb_owed.values()), 2) == JB_CONSUMO
    return plans


def fix_receipt(key: str, write: bool) -> None:
    """Porta la ricevuta 'John Barrille' 550 a 800 con i due pagatori veri
    (Edo 550 + Giacomo 250, ognuno debitore di se': resta a saldo zero)."""
    for e in expenses(key, str(NINA1)):
        if e["description"].strip() == "John Barrille" and float(e["cost"]) == 550.0:
            print(f"~ ricevuta John Barrille (id {e['id']}): 550 -> 800, pagatori Edo 550 + Giacomo 250")
            if write:
                res = _post(f"update_expense/{e['id']}", key, {
                    "cost": "800.00", "group_id": NINA1,
                    "users__0__user_id": EDO, "users__0__paid_share": "550.00",
                    "users__0__owed_share": "550.00",
                    "users__1__user_id": GIACOMO, "users__1__paid_share": "250.00",
                    "users__1__owed_share": "250.00"})
                if res.get("errors"):
                    sys.exit(f"update_expense ricevuta fallita: {res['errors']}")
                print("    -> aggiornata")
            return
    print("= ricevuta John Barrille 550 non trovata (gia' aggiornata?)")


def main() -> None:
    key = os.environ.get("SPLITWISE_API_KEY") or sys.exit("SPLITWISE_API_KEY non impostata")
    write = "--write" in sys.argv
    name = dict(NAME_MAP)

    have: dict[int, dict[str, dict]] = {NINA1: {}, NINA2: {}}
    for g in (NINA1, NINA2):
        for e in expenses(key, str(g)):
            for mk in re.findall(r"\[nina-cambusa:[a-z0-9_]+\]", e.get("details") or ""):
                have[g][mk] = e

    created = 0
    for p in build():
        mark = f"[nina-cambusa:{p['slug']}]"
        gname = "Nina I" if p["group"] == NINA1 else "Nina II"
        old = have[p["group"]].get(mark)
        same = old and float(old["cost"]) == p["cost"] and all(
            abs(float(next((u[f"{k}_share"] for u in old["users"]
                            if u["user"]["id"] == uid), 0)) - s) <= 0.01
            for k, plan_shares in (("owed", p["owed"]), ("paid", p["paid"]))
            for uid, s in plan_shares.items())
        if same:
            print(f"= {p['desc']} ({gname}): gia' presente e identica, salto"); continue
        verb = f"~ (aggiorno {old['cost']} -> {p['cost']:.2f})" if old else "+"
        print(f"{verb} {gname} · {p['desc']}: {p['cost']:.2f} EUR")
        print("    anticipano: " + ", ".join(f"{name.get(u, u)} {s:.2f}" for u, s in p["paid"].items()))
        print("    quote:      " + ", ".join(f"{name.get(u, u)} {s:.2f}" for u, s in sorted(
            p["owed"].items(), key=lambda t: -t[1])))
        if not write:
            continue
        payload = {"cost": f"{p['cost']:.2f}", "description": p["desc"],
                   "details": p["note"] + " " + mark, "group_id": p["group"],
                   "currency_code": "EUR", "date": DATE}
        for i, u in enumerate(sorted(set(p["paid"]) | set(p["owed"]))):
            payload[f"users__{i}__user_id"] = u
            payload[f"users__{i}__paid_share"] = f"{p['paid'].get(u, 0):.2f}"
            payload[f"users__{i}__owed_share"] = f"{p['owed'].get(u, 0):.2f}"
        op = f"update_expense/{old['id']}" if old else "create_expense"
        res = _post(op, key, payload)
        if res.get("errors"):
            sys.exit(f"{op} '{p['desc']}' fallita: {res['errors']}")
        created += 1
        print(f"    -> {'aggiornata' if old else 'creata'} (id {res['expenses'][0]['id']})")

    fix_receipt(key, write)
    print(f"\n{'Create' if write else 'Da creare'}: {created if write else 'vedi sopra'}"
          + ("" if write else " — dry-run, rilancia con --write"))


if __name__ == "__main__":
    main()
