---
description: Briefing della giornata per l'equipaggio
---
Genera il briefing per il giorno $1 (formato YYYY-MM-DD, se manca usa domani).
Usa la skill in `skills/daily-briefing/SKILL.md`. Segui l'ordine dei sei blocchi
e la gerarchia sicurezza > comfort > logistica > bellezza. Chiudi sempre con il
piano B. Ricorda: la polare è STIMATA e ogni dato `verify: true` va dichiarato.
Per i dati: `python scripts/publish.py --day $1` oppure gli script singoli
(`routing.py`, `shelter.py`). Il bollettino AM (meteoam.it/it/mare) prevale
su Open-Meteo: controllalo e segnala ogni discordanza.
