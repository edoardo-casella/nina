#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_percorsi.py — Unisce i KMZ dei singoli viaggi in un'unica mappa Google Earth.

- Legge tutti i *.kmz in data/Percorsi Google Earth/ (solo lettura).
- Ogni viaggio -> una <Folder> con nome dal file + un colore linea distinto.
- Scrive un unico data/Tutti i viaggi.kmz (+ .kml gemello).

Nessun file sorgente viene modificato. Operazione reversibile (cancella l'output).
"""
import colorsys
import io
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

KML_NS = "http://www.opengis.net/kml/2.2"
ET.register_namespace("", KML_NS)  # niente prefissi ns0: in output
_Q = lambda tag: f"{{{KML_NS}}}{tag}"  # qualifica un tag col namespace KML

# --- percorsi ---------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
SRC_DIR = DATA_DIR / "Percorsi Google Earth"
OUT_KMZ = DATA_DIR / "Tutti i viaggi.kmz"
OUT_KML = DATA_DIR / "Tutti i viaggi.kml"


def trip_name_from_file(path: Path) -> str:
    """'Sardegna \\'20.kmz' -> 'Sardegna '20' (estensione via, apostrofi normalizzati)."""
    name = path.stem
    return name.replace("’", "'").replace("`", "'").strip()


def kml_color(i: int, n: int) -> str:
    """Colore KML aabbggrr (alpha-blue-green-red) con hue distribuito sul cerchio."""
    r, g, b = colorsys.hsv_to_rgb(i / n, 0.9, 0.95)
    R, G, B = int(r * 255), int(g * 255), int(b * 255)
    return f"ff{B:02x}{G:02x}{R:02x}", f"#{R:02x}{G:02x}{B:02x}"  # (kml, hex leggibile)


def read_kml_text(path: Path) -> str:
    """Ritorna il testo KML: da .kmz (unzip del doc.kml) o da .kml (lettura diretta)."""
    if path.suffix.lower() == ".kmz":
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            target = "doc.kml" if "doc.kml" in names else next(
                (nm for nm in names if nm.lower().endswith(".kml")), None)
            if target is None:
                raise ValueError(f"Nessun .kml dentro {path.name}")
            return z.read(target).decode("utf-8")
    return path.read_text(encoding="utf-8")


def extract_placemarks(doc_xml: str):
    """Ritorna la lista di elementi <Placemark> presenti nel <Document>/<Folder>."""
    root = ET.fromstring(doc_xml)
    # i Placemark possono stare a qualsiasi profondita' -> iter su tutto l'albero
    return list(root.iter(_Q("Placemark")))


def build():
    if not SRC_DIR.is_dir():
        sys.exit(f"ERRORE: cartella sorgenti non trovata: {SRC_DIR}")

    src_files = sorted(
        (p for p in SRC_DIR.iterdir()
         if p.is_file() and p.suffix.lower() in (".kmz", ".kml")),
        key=lambda p: p.name.lower())
    if not src_files:
        sys.exit(f"ERRORE: nessun .kmz/.kml in {SRC_DIR}")

    n = len(src_files)

    # documento radice
    kml = ET.Element(_Q("kml"))
    document = ET.SubElement(kml, _Q("Document"))
    ET.SubElement(document, _Q("name")).text = "Viaggi in barca (2011-2024)"
    ET.SubElement(document, _Q("open")).text = "1"

    legend = []      # (nome, hex) per stampa a console
    folders = []     # rimandiamo l'append cosi' gli Style stanno tutti in testa

    for i, src in enumerate(src_files):
        name = trip_name_from_file(src)
        color_kml, color_hex = kml_color(i, n)
        style_id = f"trip{i}"

        # Style del viaggio (linea colorata, poligono non riempito)
        style = ET.SubElement(document, _Q("Style"), {"id": style_id})
        line = ET.SubElement(style, _Q("LineStyle"))
        ET.SubElement(line, _Q("color")).text = color_kml
        ET.SubElement(line, _Q("width")).text = "3"
        poly = ET.SubElement(style, _Q("PolyStyle"))
        ET.SubElement(poly, _Q("fill")).text = "0"

        # Folder del viaggio
        folder = ET.Element(_Q("Folder"))
        ET.SubElement(folder, _Q("name")).text = name

        placemarks = extract_placemarks(read_kml_text(src))
        if not placemarks:
            print(f"  ! ATTENZIONE: nessun Placemark in {src.name}")
        for pm in placemarks:
            # rimuovi eventuale styleUrl originale (rosso) e forza quello del viaggio
            for su in pm.findall(_Q("styleUrl")):
                pm.remove(su)
            style_url = ET.Element(_Q("styleUrl"))
            style_url.text = f"#{style_id}"
            pm.insert(0, style_url)
            folder.append(pm)

        folders.append(folder)
        legend.append((name, color_hex, len(placemarks)))

    for folder in folders:
        document.append(folder)

    # serializzazione
    ET.indent(kml, space="\t")
    xml_bytes = ET.tostring(kml, encoding="UTF-8", xml_declaration=True)

    OUT_KML.write_bytes(xml_bytes)
    with zipfile.ZipFile(OUT_KMZ, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", xml_bytes)

    # legenda a console
    print(f"\n{n} viaggi uniti -> {OUT_KMZ.name} (+ {OUT_KML.name})\n")
    print("  Legenda viaggio -> colore (n. tracce):")
    for name, chex, ntr in legend:
        print(f"   {chex}  {name}  ({ntr})")
    print(f"\n  Output in: {DATA_DIR}")


if __name__ == "__main__":
    build()
