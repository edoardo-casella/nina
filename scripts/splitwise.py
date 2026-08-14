"""Cassa di bordo da Splitwise: le spese comuni le registra l'equipaggio
nell'app, la CI le legge a ogni run e la card "Cassa di bordo" resta aggiornata
da sola. Fallback: senza env o con Splitwise giu', publish.py usa
voyage.json.expenses come prima.

Env: SPLITWISE_API_KEY (API key personale da secure.splitwise.com/apps),
     SPLITWISE_GROUP_ID (id numerico del gruppo del viaggio).

Modello: ogni spesa Splitwise ha paid_share/owed_share ESATTI per utente
(anche split disuguali) -> il netto si calcola da li', non serve l'ipotesi
"parti uguali" di ledger.py. I payment (pareggi registrati in app) entrano nel
netto ma NON nel totale speso. I bonifici minimi riusano ledger.min_transfers.

Uso a mano:  python scripts/splitwise.py groups          # lista gruppi
             python scripts/splitwise.py conti <group_id> # dry-run cassa
"""
from __future__ import annotations
import json, sys, urllib.parse, urllib.request
from ledger import min_transfers

API = "https://secure.splitwise.com/api/v3.0"


def _get(path: str, key: str, **params) -> dict:
    q = urllib.parse.urlencode(params)
    # senza User-Agent "vero" il WAF di Splitwise risponde 403 a Python-urllib
    req = urllib.request.Request(f"{API}/{path}" + (f"?{q}" if q else ""),
                                 headers={"Authorization": f"Bearer {key}",
                                          "User-Agent": "nina-sailing-agent/1.0 github.com/edoardo-casella/nina"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def groups(key: str) -> list[dict]:
    return _get("get_groups", key)["groups"]


def expenses(key: str, group_id: str) -> list[dict]:
    out, offset = [], 0
    while True:
        page = _get("get_expenses", key, group_id=group_id,
                    limit=100, offset=offset)["expenses"]
        out += page
        if len(page) < 100:
            break
        offset += 100
    return [e for e in out if not e.get("deleted_at")]


# Splitwise user id -> nome come appare sul sito (voyage.json crew). Keyed
# per id, NON per nome: i display Splitwise sono liberi ("Gine", "Costanz",
# "matildemalanca15") e cambiabili dall'utente. Verificato via email 2026-08-14.
# Chi entra nel gruppo dopo (equipaggi 15/8 e 22/8) va aggiunto qui.
NAME_MAP = {
    20136237: "Edo C",        # Edoardo Casella
    31837892: "Ginevra L",    # "Gine"
    35409668: "Giacomo N",    # Giacomo Nassi
    35630477: "Bernardo B",   # "bernardo bolgeri"
    55090008: "Bianca M",     # "Bi Mazzoli"
    92858746: "Matilde M",    # "matildemalanca15" (Malanca)
    100252186: "Isabella",    # Isabella Wood
    14444843: "Ilaria C.",    # Ilaria Chiuchiolo
    99385232: "Matilde C.",   # "mati" (l'altra Matilde)
    16854700: "Lorenzo C.",   # "Costanz" (Costanzo, il Presidente)
    104408857: "Vale F",      # Valentina Franchi
}


def _display(u: dict) -> str:
    """Nome del sito da NAME_MAP; fuori mappa: 'Nome C' dai dati Splitwise."""
    mapped = NAME_MAP.get(u.get("id"))
    if mapped:
        return mapped
    first = (u.get("first_name") or "").strip() or "?"
    last = (u.get("last_name") or "").strip()
    return f"{first} {last[0]}" if last else first


def conti_data(key: str, group_id: str) -> dict:
    """spent/transfers/expenses per il blob 'conti' (stessa shape del frontend)."""
    exp = expenses(key, group_id)
    net: dict[str, float] = {}
    rows = []
    spent = 0.0
    for e in exp:
        cost = float(e["cost"])
        for u in e.get("users", []):
            name = _display(u.get("user") or {})
            net[name] = round(net.get(name, 0.0)
                              + float(u.get("paid_share") or 0)
                              - float(u.get("owed_share") or 0), 2)
        if e.get("payment"):
            continue  # pareggio gia' fatto: conta nel netto, non nello speso
        spent += cost
        payer = next((_display(u["user"]) for u in e.get("users", [])
                      if float(u.get("paid_share") or 0) > 0), "?")
        rows.append({"date": (e.get("date") or "")[:10],
                     "desc": e.get("description") or "spesa",
                     "amount": round(cost, 2), "paid_by": payer,
                     "currency": e.get("currency_code")})
    rows.sort(key=lambda r: r["date"], reverse=True)
    non_eur = sorted({r["currency"] for r in rows if r["currency"] != "EUR"})
    for r in rows:
        del r["currency"]
    return {"spent": round(spent, 2),
            "transfers": min_transfers(net),
            "expenses": rows,
            "non_eur": non_eur}  # se non vuoto: valute miste, i totali mentono


if __name__ == "__main__":
    import os
    key = os.environ.get("SPLITWISE_API_KEY")
    if not key:
        sys.exit("SPLITWISE_API_KEY non impostata")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "groups"
    if cmd == "groups":
        for g in groups(key):
            print(f"{g['id']:>10}  {g['name']}  ({len(g.get('members', []))} membri)")
    elif cmd == "conti":
        c = conti_data(key, sys.argv[2])
        print(f"Speso: {c['spent']:.2f} EUR su {len(c['expenses'])} spese"
              + (f"  ⚠️ valute non-EUR: {c['non_eur']}" if c["non_eur"] else ""))
        for t in c["transfers"]:
            print(f"  {t['from']} -> {t['to']}  {t['amount']:.2f}")
        for r in c["expenses"][:10]:
            print(f"  {r['date']}  {r['amount']:>8.2f}  {r['desc']}  ({r['paid_by']})")
