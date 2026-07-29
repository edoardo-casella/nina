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
from core import load, ROOT, nights_aboard
from provisioning import shopping_list, SAFETY_MARGIN

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
# "Pasta / riso (g)" e "Vino (bottiglie)" NON ci sono: hanno un dettaglio dedicato
# (pasta_breakdown/alcolici_lines) perche' vanno spezzati per persona/preferenza,
# non trattati come un blocco unico.
PACKAGING = {
    "Acqua in bottiglia (L)": (9, "cassa da 6x1,5L"),
    "Pane (g)": (500, "pagnotta/pacco da 500g"),
    "Verdura fresca (g)": (1000, "kg"),
    "Frutta (g)": (1000, "kg"),
    "Carne / pesce (g)": (1000, "kg"),
    "Uova (n)": (30, "cassa da 30"),
    "Formaggio (g)": (1000, "kg (sottovuoto)"),
    "Latte (ml)": (1000, "cartone da 1L"),
    "Caffe' (dosi)": (15, "confezione da 250g (~15 dosi moka)"),
    "Birra (n)": (24, "cassa da 24 lattine"),
    "Snack / biscotti (g)": (300, "confezione da 300g"),
    "Ghiaccio (kg)": (2, "sacco da 2kg"),
}

# Canale d'acquisto consigliato per voce:
#  - "online": generico/pesante/dura a lungo -> ok ordinarlo in anticipo (es. Conad
#    Spesa Online, area Olbia-Tempio copre Arzachena/Cannigione) e farselo consegnare
#    prima dell'8, o ritiro in negozio.
#  - "di persona": freschezza (deperibili) O specialita' locale che l'equipaggio ha
#    esplicitamente segnalato di voler provare (pecorino sardo) -> meglio scegliere
#    sul posto (mercato/enoteca/pescheria) che affidarsi a un catalogo online.
CHANNEL = {
    "Acqua in bottiglia (L)": "online",
    "Pane (g)": "di persona",
    "Verdura fresca (g)": "di persona",
    "Frutta (g)": "di persona",
    "Carne / pesce (g)": "di persona",
    "Uova (n)": "online",
    "Formaggio (g)": "di persona",     # pecorino sardo e' la specialita' piu' richiesta (11x)
    "Latte (ml)": "di persona",
    "Caffe' (dosi)": "online",
    "Birra (n)": "online",
    "Snack / biscotti (g)": "online",
    "Ghiaccio (kg)": "di persona",     # si scioglie: va preso il giorno stesso
}

# Dispensa/conserve "boat essential" (fonte: consigli cambusa charter/vela — olio,
# sale, scatolame, legumi, pane secco). Non erano in RATES/provisioning.py: quantita'
# a occhio per l'intera crociera (non scalate a persona-giorno come il resto, sono
# scorte-cuscinetto), da aggiustare liberamente. Alcune coprono cibi immancabili
# segnalati nel questionario (tonno: Giulia N/Gabri M; acciughe: Lavinia P).
DISPENSA_ESSENZIALI = [
    {"voce": "Tonno in scatola (80g)", "quantita_totale": "-", "confezioni": 24, "formato": "scatolette da 80g", "canale": "online"},
    {"voce": "Acciughe/alici (sottolio o sotto sale)", "quantita_totale": "-", "confezioni": 8, "formato": "vasetti/latte", "canale": "online"},
    {"voce": "Legumi cotti (fagioli/ceci)", "quantita_totale": "-", "confezioni": 12, "formato": "barattoli da 400g", "canale": "online"},
    {"voce": "Pomodori pelati / passata", "quantita_totale": "-", "confezioni": 10, "formato": "bottiglie/lattine da 500g-700g", "canale": "online"},
    {"voce": "Olio extravergine d'oliva", "quantita_totale": "-", "confezioni": 4, "formato": "bottiglie da 1L", "canale": "online"},
    {"voce": "Sale grosso + fino", "quantita_totale": "-", "confezioni": 2, "formato": "pacchi da 1kg", "canale": "online"},
    {"voce": "Crackers / gallette / pane secco", "quantita_totale": "-", "confezioni": 10, "formato": "confezioni da 250g", "canale": "online"},
    {"voce": "Marmellata", "quantita_totale": "-", "confezioni": 4, "formato": "vasetti da 350g", "canale": "online"},
]


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


# --- Pasta/riso dettagliato: riso vs pasta, + quota senza glutine per chi ne ha
# bisogno (celiachia/intolleranza reale, rilevata dal testo libero delle allergie,
# non da un campo dedicato del form). Stessa RATE combinata di provisioning.py
# (120 g/persona/giorno), solo spezzata invece che in un unico blocco.
PASTA_RATE_TOTALE = 120  # g/persona/giorno (invariato)
RISO_QUOTA = 0.20
PASTA_QUOTA = 0.80
GLUTEN_KEYWORDS = ("glutine", "celiac")


def gluten_free_person_days(v: dict, prefs: dict) -> tuple[int, list[str]]:
    n2id = name_to_crew_id()
    days, nomi = 0, []
    for m in v["crew"]:
        p = prefs.get(n2id.get(m["name"], m["id"]))
        if p and any(k in p["allergie"].lower() for k in GLUTEN_KEYWORDS):
            days += nights_aboard(m)
            nomi.append(m["name"])
    return days, nomi


def pasta_breakdown(v: dict, prefs: dict, total_person_days: int) -> list[dict]:
    gf_days, gf_nomi = gluten_free_person_days(v, prefs)
    normal_days = max(total_person_days - gf_days, 0)
    riso_g = PASTA_RATE_TOTALE * RISO_QUOTA * total_person_days * SAFETY_MARGIN
    pasta_normale_g = PASTA_RATE_TOTALE * PASTA_QUOTA * normal_days * SAFETY_MARGIN
    pasta_gf_g = PASTA_RATE_TOTALE * PASTA_QUOTA * gf_days * SAFETY_MARGIN
    righe = [
        {"voce": "Riso", "quantita_totale": round(riso_g, 1),
         "confezioni": math.ceil(riso_g / 1000), "formato": "pacchi da 1kg"},
        {"voce": "Pasta corta (normale)", "quantita_totale": round(pasta_normale_g / 2, 1),
         "confezioni": math.ceil((pasta_normale_g / 2) / 500), "formato": "pacchi da 500g"},
        {"voce": "Pasta lunga/spaghetti (normale)", "quantita_totale": round(pasta_normale_g / 2, 1),
         "confezioni": math.ceil((pasta_normale_g / 2) / 500), "formato": "pacchi da 500g"},
    ]
    if gf_days:
        righe.append({
            "voce": f"Pasta SENZA GLUTINE ({', '.join(gf_nomi)})",
            "quantita_totale": round(pasta_gf_g, 1),
            "confezioni": math.ceil(pasta_gf_g / 500), "formato": "pacchi da 500g",
        })
    return righe


# --- Alcolici/aperitivo: quantita' pesate sulle notti a bordo di CHI l'ha
# effettivamente richiesto (non un conteggio flat), con una frequenza di consumo
# assunta (ogni_n_giorni) - stima dichiarata, non una scienza esatta.
APERITIVO_ITEMS = {
    "Aperol (per lo spritz)": {"ogni_n_giorni": 2, "ml_per_persona": 50, "ml_confezione": 700, "formato": "bottiglie da 70cl"},
    "Prosecco / spumante": {"ogni_n_giorni": 2, "ml_per_persona": 100, "ml_confezione": 750, "formato": "bottiglie da 75cl"},
    "Vino bianco": {"ogni_n_giorni": 1, "ml_per_persona": 150, "ml_confezione": 750, "formato": "bottiglie da 75cl"},
}
ACQUA_TONICA_ML_PER_SPRITZ = 150  # mixer per l'Aperol: dimensionata sui suoi stessi consumi, non sul suo conteggio isolato (1 sola richiesta esplicita)


def bibite_person_days(v: dict, prefs: dict) -> Counter:
    """Per ogni bevanda, somma le notti a bordo di chi l'ha scelta (pesato sulla
    permanenza reale — chi sta 20 giorni conta piu' di chi ne sta 3)."""
    n2id = name_to_crew_id()
    pd = Counter()
    for m in v["crew"]:
        p = prefs.get(n2id.get(m["name"], m["id"]))
        if not p:
            continue
        for b in p["bibite"]:
            pd[b] += nights_aboard(m)
    return pd


def alcolici_lines(v: dict, prefs: dict) -> list[dict]:
    pd = bibite_person_days(v, prefs)
    righe = []
    for voce, cfg in APERITIVO_ITEMS.items():
        servings = pd.get(voce, 0) / cfg["ogni_n_giorni"]
        ml_tot = servings * cfg["ml_per_persona"]
        righe.append({
            "voce": voce, "quantita_totale": round(ml_tot / 1000, 1),
            "confezioni": math.ceil(ml_tot / cfg["ml_confezione"]) if ml_tot else 0,
            "formato": cfg["formato"],
        })
    aperol_servings = pd.get("Aperol (per lo spritz)", 0) / APERITIVO_ITEMS["Aperol (per lo spritz)"]["ogni_n_giorni"]
    tonica_ml = aperol_servings * ACQUA_TONICA_ML_PER_SPRITZ
    righe.append({
        "voce": "Acqua tonica/gassata (mixer per Aperol)", "quantita_totale": round(tonica_ml / 1000, 1),
        "confezioni": math.ceil(tonica_ml / 1000) if tonica_ml else 0, "formato": "bottiglie da 1L",
    })
    return [r for r in righe if r["confezioni"] > 0]

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

    dettagliate_a_parte = {"Pasta / riso (g)", "Vino (bottiglie)"}
    return {
        "spesa_grossa": {
            "giorno": start,
            "non_deperibile_intera_crociera": {k: q for k, q in durables_full["items"].items()
                                                if k not in PERISHABLES and k not in dettagliate_a_parte},
            "deperibile_prima_tratta": {k: q for k, q in perishables_leg1["items"].items()
                                        if k in PERISHABLES},
            "budget_stimato_eur": durables_full["budget_eur"],
            "pasta_dettaglio": pasta_breakdown(v, prefs, durables_full["person_days"]),
            "alcolici_dettaglio": alcolici_lines(v, prefs),
            "dispensa_essenziali": DISPENSA_ESSENZIALI,
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
    # Alcolici, pasta/riso e dispensa/conserve: sempre online (generici, non deperibili).
    righe = (detailed_lines(tutte_le_voci)
             + [{**x, "canale": "online"} for x in g["dispensa_essenziali"]]
             + [{**x, "canale": "online"} for x in g["pasta_dettaglio"]]
             + [{**x, "canale": "online"} for x in g["alcolici_dettaglio"]])
    for canale, titolo in (("online", "ONLINE (ordina in anticipo, ritiro/consegna prima dell'8)"),
                           ("di persona", "DI PERSONA (mercato/pescheria/enoteca l'8 mattina)")):
        print(f"{titolo}:")
        for x in righe:
            if x["canale"] != canale:
                continue
            print(f"  {x['voce']:<45} {x['quantita_totale']:>8}  ->  {x['confezioni']:>3}x {x['formato']}")
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
