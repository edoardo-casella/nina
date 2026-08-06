"""Esporta il piano cambusa in un Excel condivisibile con l'equipaggio.

Fonte unica: build_plan() di cambusa_plan.py (stessi numeri della console).
PRIVACY (regola del progetto, il file gira su OneDrive condiviso):
  - niente nomi legati ad allergie: la riga "Pasta SENZA GLUTINE (nomi)"
    perde i nomi nel foglio; il dettaglio resta solo nella console locale
  - niente note dal questionario (preferenze/allergie): il foglio ha solo
    quantita' aggregate

Output: data/Cambusa 2026.xlsx (gitignorato: data/*.xlsx). Il file va poi
caricato su OneDrive; rigenerarlo quando cambiano equipaggio o questionari.

  python scripts/cambusa_xlsx.py
"""
from __future__ import annotations
import datetime as dt
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from core import load, ROOT
from cambusa_plan import build_plan, detailed_lines

OUT = ROOT / "data" / "Cambusa 2026.xlsx"

HEAD_FILL = PatternFill("solid", fgColor="1F4E5F")
HEAD_FONT = Font(bold=True, color="FFFFFF")
CAT_FILL = PatternFill("solid", fgColor="E8F0F2")

# categoria per voce: prefissi (il nome esatto puo' cambiare, es. quantita' tra
# parentesi); l'ordine della lista e' l'ordine dei blocchi nel foglio
CATEGORIE = [
    ("Liquidi", ("Acqua in bottiglia", "Coca Cola", "Estathé", "Succhi", "Sprite",
                 "Gatorade", "Birra analcolica", "Acqua tonica")),
    ("Alcolici", ("Birra (n)", "Aperol", "Prosecco", "Vino bianco", "Cannonau",
                  "Malvasia", "Mirto", "Filu")),
    ("Pasta e riso", ("Riso", "Pasta ")),
    ("Dispensa", ("Tonno", "Acciughe", "Legumi", "Pomodori", "Olio", "Sale grosso",
                  "Crackers", "Marmellata")),
    ("Colazione e snack", ("Caffe", "Caffe'", "Snack")),
    ("Freschi (mercato dell'8)", ("Pane (g)", "Verdura", "Frutta", "Carne", "Latte",
                                  "Formaggio", "Uova", "Ghiaccio")),
    ("Pulizia e consumabili", ("Carta igienica", "Rotoloni", "Detersivo", "Spugne",
                               "Panni", "Sacchi", "Sacchetti", "Sgrassatore",
                               "Detergente", "Sapone", "Gel igienizzante", "Pellicola",
                               "Tovaglioli", "Mollette", "Antizanzare", "Dopopuntura",
                               "Guanti", "Accendini")),
]


def categoria(voce: str) -> str:
    for cat, prefissi in CATEGORIE:
        if any(voce.startswith(p) for p in prefissi):
            return cat
    return "Altro"


def _san(voce: str) -> str:
    """La riga senza glutine perde i nomi (allergie mai fuori dal locale)."""
    return re.sub(r"^Pasta SENZA GLUTINE \(.*\)$", "Pasta SENZA GLUTINE", voce)


def _sheet_header(ws, cols, widths):
    for i, (name, w) in enumerate(zip(cols, widths), start=1):
        c = ws.cell(row=1, column=i, value=name)
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}1"


def build_xlsx() -> None:
    v = load()
    r = build_plan(v)
    g = r["spesa_grossa"]

    tutte_le_voci = {**g["non_deperibile_intera_crociera"], **g["deperibile_prima_tratta"]}
    righe = (detailed_lines(tutte_le_voci)
             + [{**x, "canale": "online"} for x in g["dispensa_essenziali"]]
             + [{**x, "canale": "online"} for x in g["pasta_dettaglio"]]
             + g["bevande_dettaglio"]
             + g["pulizia_consumabili"])
    for x in righe:
        x["voce"] = _san(x["voce"])
        x["categoria"] = categoria(x["voce"])

    wb = Workbook()

    # --- foglio 1: spesa grossa, ordinata per categoria (blocchi) poi canale
    ws = wb.active
    ws.title = "Spesa grossa 8-8"
    cols = ["Fatto", "Categoria", "Articolo", "Confezioni", "Formato",
            "Canale", "Q.ta' totale", "Note"]
    _sheet_header(ws, cols, [7, 22, 44, 11, 32, 11, 12, 28])
    ordine_cat = [c for c, _ in CATEGORIE] + ["Altro"]
    righe.sort(key=lambda x: (ordine_cat.index(x["categoria"]),
                              x["canale"] != "online", x["voce"].lower()))
    row, last_cat = 2, None
    for x in righe:
        if x["categoria"] != last_cat:
            last_cat = x["categoria"]
            c = ws.cell(row=row, column=2, value=last_cat.upper())
            c.font = Font(bold=True)
            for i in range(1, len(cols) + 1):
                ws.cell(row=row, column=i).fill = CAT_FILL
            row += 1
        ws.cell(row=row, column=2, value=x["categoria"])
        ws.cell(row=row, column=3, value=x["voce"])
        ws.cell(row=row, column=4, value=x["confezioni"]).alignment = Alignment(horizontal="center")
        ws.cell(row=row, column=5, value=x["formato"])
        ws.cell(row=row, column=6, value=x["canale"])
        q = x["quantita_totale"]
        ws.cell(row=row, column=7, value=q if q != "-" else None)
        row += 1

    # --- foglio 2: rifornimenti ai cambi equipaggio (deperibili per tratta)
    ws2 = wb.create_sheet("Rifornimenti")
    _sheet_header(ws2, ["Fatto", "Tratta", "Persona-giorno", "Articolo", "Quantita'"],
                  [7, 26, 15, 30, 12])
    row = 2
    for leg in r["rifornimenti_successivi"]:
        for voce, q in leg["deperibile"].items():
            ws2.cell(row=row, column=2, value=leg["tratta"])
            ws2.cell(row=row, column=3, value=leg["persona_giorno"])
            ws2.cell(row=row, column=4, value=voce)
            ws2.cell(row=row, column=5, value=q)
            row += 1

    # --- foglio 3: leggimi
    ws3 = wb.create_sheet("Leggimi")
    ws3.column_dimensions["A"].width = 110
    note = [
        "CAMBUSA NINA 2026 — baseline di spesa condivisa",
        "",
        f"Spesa grossa il {g['giorno']} (primo imbarco): tutto il non deperibile per l'intera crociera",
        "+ i freschi della prima tratta. I fogli 'Rifornimenti' coprono i deperibili ai cambi equipaggio.",
        f"Budget stimato spesa grossa: ~{g['budget_stimato_eur']} EUR.",
        "",
        "Canale 'online' = ordinabile in anticipo (es. Conad Spesa Online, area Olbia-Tempio,",
        "consegna/ritiro prima dell'8). Canale 'di persona' = mercato/pescheria/enoteca l'8 mattina",
        "(freschi e specialita' locali).",
        "",
        "Come si usa: spunta la colonna 'Fatto' man mano; se cambi quantita' o aggiungi righe,",
        "scrivilo in Note cosi' lo skipper riallinea il piano.",
        "Le quantita' vengono dal questionario equipaggio (aggregate, pesate sulle notti a bordo",
        "di ciascuno, con margine di sicurezza). Niente nomi ne' dati personali in questo file:",
        "allergie e preferenze singole le gestisce lo skipper a parte.",
        "",
        "NB carta igienica: SOLO quella dissolvibile per WC marini (quella normale intasa le pompe).",
        "",
        f"Generato il {dt.date.today().isoformat()} da scripts/cambusa_xlsx.py — rigenerare se cambia l'equipaggio.",
    ]
    for i, t in enumerate(note, start=1):
        c = ws3.cell(row=i, column=1, value=t)
        if i == 1:
            c.font = Font(bold=True, size=13)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"Scritto {OUT} — {len(righe)} righe spesa grossa, "
          f"{sum(len(l['deperibile']) for l in r['rifornimenti_successivi'])} righe rifornimenti")


if __name__ == "__main__":
    build_xlsx()
