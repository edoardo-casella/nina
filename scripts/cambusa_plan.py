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
import argparse, json, math
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

# Confezionamento tipico italiano, per convertire i totali (kg/L/pz) in righe
# d'ordine reali. Stima: aggiustare qui se il formato reale del negozio e' diverso.
PACKAGING = {
    "Acqua in bottiglia (L)": (9, "cassa da 6x1,5L"),
    "Pasta / riso (g)": (500, "pacco da 500g"),
    "Pane (g)": (500, "pagnotta/pacco da 500g"),
    "Verdura fresca (g)": (1000, "kg"),
    "Frutta (g)": (1000, "kg"),
    "Carne / pesce (g)": (1000, "kg"),
    "Uova (n)": (30, "cassa da 30"),
    "Formaggio (g)": (1000, "kg (sottovuoto)"),
    "Latte (ml)": (1000, "cartone da 1L"),
    "Caffe' (dosi)": (15, "confezione da 250g (~15 dosi moka)"),
    "Birra (n)": (24, "cassa da 24 lattine"),
    "Vino (bottiglie)": (6, "cassa da 6 bottiglie"),
    "Snack / biscotti (g)": (300, "confezione da 300g"),
    "Ghiaccio (kg)": (2, "sacco da 2kg"),
}

# Canale d'acquisto consigliato per voce:
#  - "online": generico/pesante/dura a lungo -> ok ordinarlo in anticipo (es. Conad
#    Spesa Online, area Olbia-Tempio copre Arzachena/Cannigione) e farselo consegnare
#    prima dell'8, o ritiro in negozio.
#  - "di persona": freschezza (deperibili) O specialita' locale che l'equipaggio ha
#    esplicitamente segnalato di voler provare (pecorino sardo, vino locale) -> meglio
#    scegliere sul posto (mercato/enoteca/pescheria) che affidarsi a un catalogo online.
CHANNEL = {
    "Acqua in bottiglia (L)": "online",
    "Pasta / riso (g)": "online",
    "Pane (g)": "di persona",
    "Verdura fresca (g)": "di persona",
    "Frutta (g)": "di persona",
    "Carne / pesce (g)": "di persona",
    "Uova (n)": "online",
    "Formaggio (g)": "di persona",     # pecorino sardo e' la specialita' piu' richiesta (11x)
    "Latte (ml)": "di persona",
    "Caffe' (dosi)": "online",
    "Birra (n)": "online",
    "Vino (bottiglie)": "di persona",  # Vermentino/Rose' corso locali richiesti esplicitamente
    "Snack / biscotti (g)": "online",
    "Ghiaccio (kg)": "di persona",     # si scioglie: va preso il giorno stesso
}


def detailed_lines(items: dict) -> list[dict]:
    """Converte {voce: quantita'} in righe d'ordine: confezioni da comprare + canale."""
    lines = []
    for item, qty in items.items():
        size, formato = PACKAGING.get(item, (1, "unita'"))
        lines.append({
            "voce": item,
            "quantita_totale": qty,
            "confezioni": math.ceil(qty / size),
            "formato": formato,
            "canale": CHANNEL.get(item, "di persona"),
        })
    return lines

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
    tutte_le_voci = {**g["non_deperibile_intera_crociera"], **g["deperibile_prima_tratta"]}
    righe = detailed_lines(tutte_le_voci)
    for canale, titolo in (("online", "ONLINE (ordina in anticipo, ritiro/consegna prima dell'8)"),
                           ("di persona", "DI PERSONA (mercato/pescheria/enoteca l'8 mattina)")):
        print(f"{titolo}:")
        for x in righe:
            if x["canale"] != canale:
                continue
            print(f"  {x['voce']:<26} {x['quantita_totale']:>10}  ->  {x['confezioni']:>3}x {x['formato']}")
        print()

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
