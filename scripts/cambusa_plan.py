"""Piano cambusa in due fasi, incrociando le preferenze private del questionario
equipaggio (cibo immancabile, specialita', bevande, allergie - dati SOLO locali,
mai pubblicati sul sito: vivono in data/jotform-inbox/, gitignored) con le
quantita' scalate da provisioning.py:

  - "spesa grossa" il giorno del primo imbarco di massa: tutto il non deperibile
    per l'INTERA crociera (non scade) + il deperibile solo per la prima tratta
  - "rifornimenti": il deperibile per ogni tratta successiva, ai cambi equipaggio

Le note di preferenza (must-have, allergie, bevande piu' richieste, specialita'
piu' gettonate) sono un aiuto per il menu, non un algoritmo di menu completo.
"""
from __future__ import annotations
import argparse, json
from collections import Counter
from core import load, ROOT
from provisioning import shopping_list

INBOX = ROOT / "data" / "jotform-inbox"
CREWJSON = ROOT / "site" / "data" / "crew.json"


def name_to_crew_id() -> dict:
    """name (es. 'Bianca M', come in voyage.json) -> crew_id lungo (es. 'bianca-m',
    come nei file jotform-inbox). voyage.json usa id brevi (ec/bib/...) diversi dal
    crew_id: il nome e' l'unica chiave in comune (stesso trucco di build_arrivi()
    in scripts/publish.py)."""
    people = json.loads(CREWJSON.read_text(encoding="utf-8"))["people"]
    return {p["name"]: p["id"] for p in people}

# Voci che vanno comprate a ridosso del consumo (marciscono/scadono);
# tutto il resto in RATES e' considerato non deperibile: si carica in blocco l'8.
PERISHABLES = {
    "Pane (g)", "Verdura fresca (g)", "Frutta (g)", "Carne / pesce (g)",
    "Latte (ml)", "Ghiaccio (kg)",
}

NO_ALLERGY_ANSWERS = {"no", "no, nessuna", "nessuna", "no allergie", ""}


def load_preferences() -> dict:
    """crew_id -> preferenze dallo staging Jotform locale (mai pubblicato)."""
    prefs = {}
    if not INBOX.exists():
        return prefs
    for f in INBOX.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        cid = d.get("crew_id")
        if not cid:
            continue
        pub, ris = d.get("pubblicabili", {}), d.get("riservati_non_pubblicare", {})
        prefs[cid] = {
            "cibo_immancabile": pub.get("cibo_immancabile"),
            "specialita_sarde": ris.get("specialita_sarde") or [],
            "allergie": (ris.get("allergie_intolleranze") or "").strip(),
            "bibite": ris.get("bibite") or [],
        }
    return prefs


def leg_boundaries(v: dict) -> list[str]:
    """Date uniche di imbarco/sbarco, ordinate: delimitano le tratte cambusa."""
    dates = sorted({m["board"] for m in v["crew"]} | {m["leave"] for m in v["crew"]})
    return dates


def preference_notes(v: dict, prefs: dict) -> dict:
    must_have, allergie, missing = [], [], []
    bibite, curiosita = Counter(), Counter()
    n2id = name_to_crew_id()
    for m in v["crew"]:
        p = prefs.get(n2id.get(m["name"], m["id"]))
        if not p:
            missing.append(m["name"])
            continue
        if p["cibo_immancabile"]:
            must_have.append(f"{m['name']}: {p['cibo_immancabile']}")
        if p["allergie"] and p["allergie"].lower() not in NO_ALLERGY_ANSWERS:
            allergie.append(f"{m['name']}: {p['allergie']}")
        for b in p["bibite"]:
            bibite[b] += 1
        for s in p["specialita_sarde"]:
            if "va bene tutto" not in s.lower():
                curiosita[s] += 1
    return {
        "cibo_immancabile_per_persona": must_have,
        "allergie_da_rispettare": allergie,
        "bevande_piu_richieste": bibite.most_common(10),
        "specialita_piu_gettonate": curiosita.most_common(10),
        "equipaggio_senza_questionario": missing,
    }


def build_plan(v: dict) -> dict:
    prefs = load_preferences()
    legs = leg_boundaries(v)
    start, end = legs[0], legs[-1]
    durables_full = shopping_list(v, start, end)
    first_leg_end = legs[1] if len(legs) > 1 else end
    perishables_leg1 = shopping_list(v, start, first_leg_end)

    rifornimenti = []
    for i in range(1, len(legs) - 1):
        leg_start, leg_end = legs[i], legs[i + 1]
        r = shopping_list(v, leg_start, leg_end)
        rifornimenti.append({
            "tratta": f"{leg_start} -> {leg_end}",
            "persona_giorno": r["person_days"],
            "deperibile": {k: q for k, q in r["items"].items() if k in PERISHABLES},
        })

    return {
        "spesa_grossa": {
            "giorno": start,
            "non_deperibile_intera_crociera": {k: q for k, q in durables_full["items"].items()
                                                if k not in PERISHABLES},
            "deperibile_prima_tratta": {k: q for k, q in perishables_leg1["items"].items()
                                        if k in PERISHABLES},
            "budget_stimato_eur": durables_full["budget_eur"],
        },
        "rifornimenti_successivi": rifornimenti,
        "note_preferenze": preference_notes(v, prefs),
    }


def _print_items(items: dict) -> None:
    for k, q in items.items():
        print(f"  {k:<30} {q}")


if __name__ == "__main__":
    argparse.ArgumentParser(description="Piano cambusa in due fasi (spesa grossa + rifornimenti)").parse_args()
    v = load()
    r = build_plan(v)

    g = r["spesa_grossa"]
    print(f"=== SPESA GROSSA — {g['giorno']} ===  budget ~{g['budget_stimato_eur']} EUR\n")
    print("Non deperibile (dura tutta la crociera):")
    _print_items(g["non_deperibile_intera_crociera"])
    print("\nDeperibile (solo per la prima tratta):")
    _print_items(g["deperibile_prima_tratta"])

    for leg in r["rifornimenti_successivi"]:
        print(f"\n=== RIFORNIMENTO — {leg['tratta']} ({leg['persona_giorno']} persona-giorno) ===")
        _print_items(leg["deperibile"])

    n = r["note_preferenze"]
    print("\n=== NOTE PER IL MENU (dal questionario, mai pubblicate) ===")
    print("\nCibo immancabile per persona:")
    for x in n["cibo_immancabile_per_persona"]:
        print(f"  - {x}")
    if n["allergie_da_rispettare"]:
        print("\nALLERGIE/INTOLLERANZE DA RISPETTARE:")
        for x in n["allergie_da_rispettare"]:
            print(f"  ! {x}")
    print("\nBevande piu' richieste:")
    for k, c in n["bevande_piu_richieste"]:
        print(f"  {c}x  {k}")
    print("\nSpecialita' locali piu' gettonate (da provare insieme):")
    for k, c in n["specialita_piu_gettonate"]:
        print(f"  {c}x  {k}")
    if n["equipaggio_senza_questionario"]:
        print("\nSenza questionario — trattati come media (nessuna preferenza/allergia")
        print("specifica da rispettare, gia' contati nelle quantita' sopra):")
        for x in n["equipaggio_senza_questionario"]:
            print(f"  - {x}")
