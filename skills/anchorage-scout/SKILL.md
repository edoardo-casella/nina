---
name: anchorage-scout
description: Sceglie dove ancorare stanotte in base al vento previsto, calcolando lo Shelter Score con semaforo verde/giallo/rosso per ogni rada, e suggerisce alternative se la rada scelta e' esposta. USA QUESTA SKILL ogni volta che si parla di ancoraggio, rada, baia, cala, "dove dormiamo", "e' riparata?", "regge il Maestrale?", "dove ci ripariamo", oppure quando il router propone una destinazione e va verificato il riparo notturno.
---

# Anchorage Scout

Una rada e' buona se il vento previsto **non entra dal suo settore aperto**.

## Il modello

Ogni rada in `data/anchorages.json` ha:
- `exposed_from` / `exposed_to`: il settore di gradi veri (senso orario) da cui entrano vento e mare
- `fetch_km`: mare libero a monte. 40 km di fetch con 20 kn fanno onda ben peggiore di 10 km con 20 kn.

`scripts/shelter.py` calcola:
- vento **dentro** il settore -> esposizione = f(intensita', fetch) -> rosso o giallo
- vento **fuori** dal settore -> punteggio cresce col margine angolare -> verde
- sotto gli 8 kn quasi tutto e' verde (ma attenzione alle brezze termiche serali)

## Comandi

```bash
python scripts/shelter.py --twd 315 --tws 22                    # classifica con vento dato
python scripts/shelter.py --from-wp spargi --day 2026-08-12     # usa la previsione delle 21:00
```

## Come rispondere

Presentare **le prime tre rade**, non solo la migliore, con il perche' in una riga. Poi:

1. Segnalare se il vento **gira** durante la notte: una rada verde alle 21 puo' essere rossa alle 4. Controllare `weather.combined` su tutta la notte, non su un'ora sola.
2. Ricordare i vincoli non meteorologici: zone A del Parco della Maddalena (divieto di ancoraggio), boe obbligatorie, riserve francesi (Lavezzi, Cerbicale), profondita' contro il pescaggio.
3. Se `verify: true`: coordinate e settori sono **stimati**, vanno confrontati col portolano (Imray, Navicarte).
4. La tenuta del fondo conta quanto il riparo: sabbia buona regge, posidonia no — e ancorare sulla posidonia e' vietato.

Mai concludere con "verde, vai tranquillo". Concludere con il piano B: quale rada e' raggiungibile in meno di un'ora se le cose peggiorano.
