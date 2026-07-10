---
name: waypoint-db
description: Importa i segnaposto salvati su una mappa Google My Maps (file KML) nel database del viaggio, calcola distanze e rotte fra i punti, e suggerisce luoghi aggiuntivi coerenti. USA QUESTA SKILL quando si parla di mappa, My Maps, KML, waypoint, segnaposto, coordinate, "i posti che ho salvato", distanze fra le cale, o quando si vuole aggiungere una destinazione all'itinerario.
---

# Waypoint DB

## Esportare da Google My Maps

My Maps → menu tre puntini → **Scarica KML** → spuntare "Esporta come KML" (non KMZ).
Se scarica un `.kmz`: rinominare in `.zip`, estrarre, usare `doc.kml`.

```bash
python scripts/import_kml.py mappa.kml --merge   # aggiunge i nuovi
python scripts/import_kml.py mappa.kml           # sostituisce tutto
```

Ogni waypoint importato nasce con `verify: true`. Google My Maps mette il segnaposto dove ha cliccato una persona, **non dove si puo' ancorare**: puo' essere sulla spiaggia, su uno scoglio, o su una secca. La coordinata va spostata sul punto di fonda reale leggendo la carta nautica.

## Distanze e rotte

```python
from core import load, find_wp, haversine_nm, bearing
v = load(); a, b = find_wp(v,"spargi"), find_wp(v,"lavezzi")
haversine_nm((a["lat"],a["lon"]), (b["lat"],b["lon"]))   # miglia in linea retta
bearing((a["lat"],a["lon"]), (b["lat"],b["lon"]))        # rotta vera
```

**Attenzione**: `haversine_nm` da la distanza ortodromica, cioe' **sopra la terraferma se c'e' di mezzo**. Non e' un router costiero. Per tratte che aggirano capi o isole, spezzarle in gambe con waypoint intermedi e sommare.

## Suggerire luoghi nuovi

Quando si propongono cale non presenti in mappa, per ognuna serve: coordinata, settore esposto stimato, perche' e' interessante, e **quale vincolo la rende difficile** (parco, affollamento, profondita', divieto di sbarco). Una proposta senza il suo vincolo e' pubblicita', non consiglio.

Aggiungere le nuove cale anche a `data/anchorages.json`, altrimenti `anchorage-scout` non le vede.
