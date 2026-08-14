"""Addebita gli EXTRA di bordo su Splitwise, dal foglio Excel (autorita').

Per ogni voce del catalogo Extra (Starter Pack, SUP, Assicurazione, ...) crea
UNA spesa nel gruppo: pagata da Edo C, quota esatta per persona (split
disuguali nativi), descrizione = nome voce, details = cosa comprende
(EXTRA_NOTES di build_finance). Ognuno e' addebitato SOLO nel gruppo della sua
prima settimana (chi fa piu' settimane non paga due volte). Edo escluso
(pagherebbe se stesso). Il delta quota barca (Bonifici) resta FUORI: si salda
con bonifico dal tab "Il tuo viaggio", non in app.

Idempotente: ogni spesa creata porta un marker "[nina-extra:<slug>]" nei
details; le voci gia' presenti nel gruppo vengono saltate ai run successivi
(nuovi membri nel gruppo -> la voce va aggiunta a mano o con un run dopo
delete della spesa; caso raro, si accetta).

Uso:  python scripts/splitwise_extras.py nina1            # dry-run
      python scripts/splitwise_extras.py nina1 --write    # crea le spese
Env:  SPLITWISE_API_KEY
"""
from __future__ import annotations
import datetime as dt
import json, os, re, sys, urllib.parse, urllib.request

from build_finance import EXTRA_NOTES, EXTRA_RENAMES, load_map, open_wb, read_extra
from splitwise import API, NAME_MAP, _get, expenses

GROUPS = {"nina1": 101493357, "nina2": 101863026, "nina3": 101863028}
EDO_UID = 20136237

SITE_TO_UID = {v: k for k, v in NAME_MAP.items()}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _post(path: str, key: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{API}/{path}", data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": "nina-sailing-agent/1.0 github.com/edoardo-casella/nina"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def first_group(nights: dict) -> str:
    return "nina1" if nights["s1"] else "nina2" if nights["s2"] else "nina3"


def main() -> None:
    key = os.environ.get("SPLITWISE_API_KEY") or sys.exit("SPLITWISE_API_KEY non impostata")
    gname = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "nina1"
    gid = GROUPS.get(gname) or sys.exit(f"Gruppo sconosciuto: {gname} (validi: {list(GROUPS)})")
    write = "--write" in sys.argv

    m = load_map()
    catalog, per = read_extra(open_wb()["Extra"], m)

    members = {u["id"] for u in _get(f"get_group/{gid}", key)["group"]["members"]}
    done = {mk for e in expenses(key, str(gid))
            for mk in re.findall(r"\[nina-extra:[a-z0-9_]+\]", e.get("details") or "")}

    # voce di catalogo -> {uid: share} per chi: ha quota, prima settimana = questo
    # gruppo, e' nel gruppo Splitwise, non e' Edo
    items: dict[str, dict[int, float]] = {}
    unmatched, elsewhere = set(), set()
    for eid, ex in per.items():
        p = m["by_id"][eid]
        uid = SITE_TO_UID.get(p["public_name"])
        for it in ex["items"]:
            if uid == EDO_UID:
                continue
            if first_group(ex["nights"]) != gname:
                elsewhere.add(p["public_name"]); continue
            if uid is None:
                unmatched.add(p["public_name"]); continue
            if uid not in members:
                unmatched.add(p["public_name"] + " (non ancora nel gruppo)"); continue
            items.setdefault(it["name"], {})[uid] = round(
                items.get(it["name"], {}).get(uid, 0) + it["share"], 2)

    uid_name = {v: k for k, v in SITE_TO_UID.items()}
    today = dt.date.today().isoformat()
    created = skipped = 0
    for name, shares in items.items():
        mark = f"[nina-extra:{slug(name)}]"
        cost = round(sum(shares.values()), 2)
        if mark in done:
            print(f"  = {name}: gia' addebitato, salto"); skipped += 1; continue
        note = EXTRA_NOTES.get(name) or EXTRA_NOTES.get(
            next((k for k, v in EXTRA_RENAMES.items() if v == name), ""), "")
        print(f"  + {name}: {cost:.2f} EUR su {len(shares)} persone"
              + "".join(f"\n      {uid_name[u]:<12} {s:>7.2f}" for u, s in sorted(shares.items(), key=lambda t: -t[1])))
        if not write:
            continue
        payload = {"cost": f"{cost:.2f}", "description": f"Extra · {name}",
                   "details": (note + " " if note else "") + mark,
                   "group_id": gid, "currency_code": "EUR", "date": today,
                   "users__0__user_id": EDO_UID,
                   "users__0__paid_share": f"{cost:.2f}", "users__0__owed_share": "0"}
        for i, (uid, s) in enumerate(shares.items(), start=1):
            payload[f"users__{i}__user_id"] = uid
            payload[f"users__{i}__paid_share"] = "0"
            payload[f"users__{i}__owed_share"] = f"{s:.2f}"
        res = _post("create_expense", key, payload)
        if res.get("errors"):
            sys.exit(f"create_expense '{name}' fallita: {res['errors']}")
        created += 1
        print(f"    -> creata (id {res['expenses'][0]['id']})")

    if elsewhere:
        print(f"  (prima settimana altrove, non toccati qui: {', '.join(sorted(elsewhere))})")
    if unmatched:
        print(f"  ⚠ senza utente Splitwise mappato: {', '.join(sorted(unmatched))}")
    print(f"{'Create' if write else 'Da creare'}: "
          f"{created if write else len([n for n in items if f'[nina-extra:{slug(n)}]' not in done])} spese"
          + (f", {skipped} gia' presenti" if skipped else "")
      + ("" if write else "  — dry-run, rilancia con --write"))


if __name__ == "__main__":
    main()
