---
name: weather-router
description: Valuta il meteo (vento, raffiche, onda) e decide se, quando e come navigare una tratta a vela, calcolando il Sail Score 0-100 e l'orario di partenza migliore. USA QUESTA SKILL ogni volta che si parla di previsioni, vento, Maestrale, "si parte domani?", "quale tratta facciamo", "quando conviene partire", "si naviga a vela o a motore", oppure quando serve confrontare piu' giorni o piu' rotte. Triggera anche per "meteo", "GRIB", "finestra meteo", "andatura", "bolina", "TWA".
---

# Weather Router

Risponde alla domanda vera: **non "si puo' partire", ma "vale la pena partire adesso, o fra tre ore, o domani".**

## Come funziona

`scripts/weather.py` scarica da Open-Meteo la serie oraria di vento (ECMWF, in nodi), raffiche e onda. Nessuna API key. Cache 1 h in `/tmp`.

`scripts/routing.py` calcola il **Sail Score (0-100)** per ogni ora, combinando:

| Componente | Peso | Ideale |
|---|---|---|
| Angolo al vento (TWA) | 30% | 70-140 gradi |
| Intensita' (TWS) | 25% | ~15 kn |
| Onda | 20% | sotto max_wave_comfort |
| Raffiche (gust/TWS) | 10% | rapporto basso |
| Velocita' dalla polare | 15% | verso 8.5 kn |

Poi simula la tratta **ora per ora**: la barca avanza con la velocita' che la polare le assegna nel vento di quell'ora, quindi la previsione cambia mentre naviga. Da qui l'ETA reale, non la media ottimistica.

## Regole specifiche del catamarano

- **Sotto i 45 gradi di TWA la barca non punta la destinazione**: bordeggia. La velocita' utile e' la VMG (`polar.best_upwind`), non la velocita' sull'acqua. Il router lo fa da solo e cappa il punteggio a 40. Un cat in bolina stretta e' lento e sbatte: non e' mai una "tratta figa".
- **Sopra i 165 gradi** conviene strambare: VMG da `polar.best_downwind` (tipicamente 150 gradi), punteggio cappato a 62.
- **STOP** oltre `max_tws_safe_kn` o con raffiche superiori al 130% di quella soglia.

## Comandi

```bash
python scripts/routing.py cannigione spargi --day 2026-08-12   # migliori orari di partenza
python scripts/weather.py 41.10 9.44                            # serie oraria grezza
python -c "import weather; print(weather.ensemble_spread(41.1,9.44))"  # affidabilita'
```

`ensemble_spread` confronta ECMWF e ICON: se divergono di piu' di 6 kn medi la previsione e' a **bassa affidabilita'** e non si pianifica oltre le 24 h.

## Obblighi

1. **Cross-check sempre** con il bollettino del mare dell'Aeronautica Militare (meteoam.it/it/mare) e con gli avvisi di burrasca. In caso di discordanza **prevale il bollettino ufficiale**, mai lo script.
2. Riportare l'affidabilita' (`ensemble_spread`) insieme al punteggio, sempre.
3. I modelli d'onda hanno risoluzione ~5 km: **sottocosta sono indicativi**.
4. Non presentare mai il Sail Score come autorizzazione a partire. E' un suggerimento. Decide lo skipper.
5. Se un waypoint ha `verify: true`, le coordinate non sono state controllate su carta nautica: dirlo.
