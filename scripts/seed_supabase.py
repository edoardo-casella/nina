"""Seed una-tantum dell'area riservata Supabase (vedi docs/LANCIO-EVERYWAVES.md).

Carica:
  - members : lo skipper (admin) + le email note dallo staging Jotform
              (data/jotform-inbox/, gitignored — le email non passano MAI dal repo).
              Gli altri membri si abilitano poi da admin.html quando chiedono accesso.
  - profiles: per ogni membro 2026, nickname (NICKS/crew2026.nick) e la scheda
              personale `q` presa dal crew.json CORRENTE. Va quindi girato PRIMA
              di rigenerare crew.json con build_crew.py (che da ora la omette).
              Dieta/allergie non vengono MAI copiate (contratto privacy).

Uso:
  python scripts/seed_supabase.py --dry-run   # mostra cosa manderebbe
  python scripts/seed_supabase.py             # esegue (serve SUPABASE_URL + SUPABASE_SERVICE_KEY)

Idempotente: usa upsert, si può rilanciare.
"""
from __future__ import annotations
import argparse, ast, json, os, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_nicks() -> dict:
    """NICKS da build_crew.py SENZA importarlo (a import-time eseguirebbe
    l'intero build, che richiede l'Excel privato): si estrae il dict via AST."""
    tree = ast.parse((ROOT / "scripts" / "build_crew.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "NICKS" for t in node.targets):
            return ast.literal_eval(node.value)
    return {}


NICKS = load_nicks()

ADMIN = {"crew_id": "edo-c", "email": "edoardo.casella@gmail.com",
         "role": "admin", "status": "approved"}
QKEYS = ("ruolo", "esperienza", "specialita", "valigia", "motto", "funfact")  # MAI dieta


def load_members() -> list[dict]:
    rows = {ADMIN["crew_id"]: dict(ADMIN)}
    inbox = ROOT / "data" / "jotform-inbox"
    for f in sorted(inbox.glob("*.json")) if inbox.is_dir() else []:
        try:
            sub = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        cid = sub.get("crew_id")
        email = (sub.get("riservati_non_pubblicare") or {}).get("email", "").strip().lower()
        if cid and email and cid not in rows:
            rows[cid] = {"crew_id": cid, "email": email, "role": "member", "status": "approved"}
    return list(rows.values())


def load_profiles() -> list[dict]:
    crew = json.loads((ROOT / "site" / "data" / "crew.json").read_text(encoding="utf-8"))
    rows, with_q = [], 0
    for p in crew["people"]:
        c26 = p.get("crew2026")
        if not c26:
            continue
        q = c26.get("q") or {}
        if q: with_q += 1
        row = {"crew_id": p["id"],
               "nick": c26.get("nick") or (p.get("nicks") or [None])[0] or NICKS.get(p["id"])}
        for k in QKEYS:
            row[k] = q.get(k)
        rows.append(row)
    if not with_q:
        print("ATTENZIONE: nessuna scheda `q` nel crew.json corrente — se e' gia' "
              "stato rigenerato senza q, recupera le schede da git (crew.json "
              "precedente) prima di seedare.", file=sys.stderr)
    return rows


def upsert(table: str, rows: list[dict]) -> None:
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("Servono le env-var SUPABASE_URL e SUPABASE_SERVICE_KEY (service role).")
    req = urllib.request.Request(
        url.rstrip("/") + f"/rest/v1/{table}",
        data=json.dumps(rows, ensure_ascii=False).encode(), method="POST",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "Prefer": "resolution=merge-duplicates,return=minimal"})
    with urllib.request.urlopen(req, timeout=30) as r:
        print(f"{table}: {len(rows)} righe upsert (HTTP {r.status})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    members, profiles = load_members(), load_profiles()
    if a.dry_run:
        print(json.dumps({"members": members, "profiles": profiles},
                         indent=2, ensure_ascii=False))
        print(f"\n-- dry run: {len(members)} members, {len(profiles)} profiles --")
    else:
        upsert("members", members)
        upsert("profiles", profiles)
