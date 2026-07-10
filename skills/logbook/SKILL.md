---
name: logbook
description: Registra il diario di bordo giorno per giorno (miglia, vento reale, rotta, rada, equipaggio, racconto) e lo trasforma in un documento leggibile a fine viaggio. USA QUESTA SKILL quando si parla di diario, logbook, giornale di bordo, "registra la giornata", "quante miglia abbiamo fatto", "com'e' andata oggi", o a fine giornata dopo il briefing.
---

# Logbook

Due livelli, entrambi necessari:

- **Dati duri**: miglia, rotta, vento reale (non previsto), ore di motore, rada, chi era a bordo.
- **Racconto**: due righe. `highlight` e' il campo che fra dieci anni varra' piu' di tutti gli altri messi insieme.

## Comandi

```bash
python scripts/logbook.py add --date 2026-08-12 --frm "Spargi" --to "Lavezzi" \
  --nm 12.4 --wind "NW 16 kn, raffiche 22" --sea "onda 0.6 m" \
  --anchorage "Cala Lazarina" --engine-hours 0.5 \
  --highlight "Traverso perfetto, 9 nodi con il gennaker. Bagno alle Lavezzi con l'acqua a 26 gradi."

python scripts/logbook.py render    # diario completo in markdown
python scripts/logbook.py totals    # miglia, ore motore, rade
```

## Perche' registrare il vento *reale*

Il vento reale confrontato col previsto e' l'unico modo per capire quanto fidarsi dei modelli **in quella zona**. Dopo cinque giorni si sa se ECMWF sottostima il Maestrale nelle Bocche di Bonifacio, e si corregge il Sail Score di conseguenza. Nessun modello globale sa cosa fa il vento fra Cavallo e Lavezzi: lo sa solo chi c'era.

## Come scrivere l'highlight

Non "bella giornata". Un dettaglio concreto e sensoriale: cosa si vedeva, cosa e' andato storto, chi ha detto cosa. La sera stessa, non il giorno dopo.

Il diario e' anche un documento: in caso di contestazione col charter, un logbook con date, rade e ore motore vale piu' di qualunque ricordo.
