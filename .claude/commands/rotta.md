---
description: Valuta una tratta e trova l'orario migliore di partenza
---
Valuta la tratta da $1 a $2 il giorno $3 con la skill in
`skills/weather-router/SKILL.md`: esegui `python scripts/routing.py $1 $2 --day $3`.
Mostra i tre orari migliori con Sail Score, ETA e percentuale a vela, poi
l'affidabilità dei modelli (`ensemble_spread`) e il promemoria del bollettino AM.
Attenzione: `haversine_nm` non evita la terraferma — se la tratta aggira un capo,
spezzala e dichiaralo.
