"""Carte LaMMA (Consorzio LaMMA, modello WW3): manifest per la dashboard.

LaMMA non pubblica API ne' GRIB: solo carte PNG per area/campo/scadenza,
riscritte in place a ogni run sotto https://www.lamma.toscana.it/models/
(2 run al giorno, init 00 e 12 UTC, online ~9 ore dopo). DATERUN.txt dice
l'init del run corrente ma non ha header CORS: il browser non puo' leggerlo.
Questo script lo legge lato CI e scrive site/data/lamma.json; la dashboard
lo usa per calcolare la scadenza "adesso" e come cache-buster delle immagini.

  python scripts/lamma.py    # scrive site/data/lamma.json e stampa i run
"""
from __future__ import annotations
import datetime as dt, json, re, sys, urllib.request
from pathlib import Path

BASE = "https://www.lamma.toscana.it/models"
PAGINA = "https://www.lamma.toscana.it/mare/modelli/vento-mare.php"

# ww3*ecm = inizializzazione IFS-ECMWF (esiste il gemello *gfs, stessa griglia)
MODELLI = {
    "hr": {"id": "ww3hrecm", "max_step": 73,   # 73 scadenze orarie = 3 giorni
           "aree": {"F": "Bonifacio", "Q": "Corsica"}},
    "lr": {"id": "ww3lrecm", "max_step": 133,  # 133 scadenze orarie ~ 5.5 giorni
           "aree": {"N": "Bonifacio", "S": "Corsica", "B": "Sardegna"}},
}
CAMPI = {"wind10": "Vento 10m", "swh": "Onda", "mwp": "Periodo onda",
         "windgust": "Raffica"}


def daterun(model_id: str) -> str:
    """Init del run corrente, es. '2026080500' (YYYYMMDDHH, UTC)."""
    url = f"{BASE}/{model_id}/last/DATERUN.txt"
    req = urllib.request.Request(url, headers={
        "User-Agent": "nina-sailing-agent/1.0 github.com/edoardo-casella/nina"})
    with urllib.request.urlopen(req, timeout=15) as r:
        text = r.read().decode("ascii", "replace")
    m = re.match(r"(\d{10})", text.strip())
    if not m:
        raise ValueError(f"DATERUN illeggibile da {url}: {text[:40]!r}")
    return m.group(1)


def build_manifest() -> dict:
    modelli = {}
    for key, cfg in MODELLI.items():
        try:
            run = daterun(cfg["id"])
        except Exception as e:
            print(f"LaMMA {cfg['id']}: DATERUN non letto ({e})", file=sys.stderr)
            continue
        modelli[key] = {"id": cfg["id"], "run": run,
                        "max_step": cfg["max_step"], "aree": cfg["aree"]}
    if not modelli:
        raise RuntimeError("nessun DATERUN LaMMA raggiungibile")
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "base": BASE, "pagina": PAGINA, "campi": CAMPI,
        # immagine: {base}/{id}/last/{campo}.{area}.{step}.png  (step 1 = init)
        "zip_tpl": "{base}/{id}/zip/lamma_{area}_{campo}.zip",
        "modelli": modelli,
    }


def write_manifest(site_dir: Path) -> dict:
    man = build_manifest()
    (site_dir / "lamma.json").write_text(
        json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    runs = ", ".join(f"{k}:{v['run']}" for k, v in man["modelli"].items())
    print(f"Carte LaMMA: manifest aggiornato ({runs})")
    return man


if __name__ == "__main__":
    write_manifest(Path(__file__).resolve().parent.parent / "site" / "data")
