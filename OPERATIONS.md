# Plancia Niña — runbook operativo di bordo

Come funziona il sistema durante la crociera, chi fa cosa e con quali strumenti.
La dashboard è https://edoardo-casella.github.io/nina/ — aggiungerla alla home
del telefono (funziona anche offline, mostra l'età dei dati).

## Cosa succede da solo (nessuno fa niente)

- **12:00 e 20:00** (ora italiana): il workflow scarica il meteo reale
  (Open-Meteo/ECMWF, onde, effemeridi met.no), ricalcola briefing, Sail Score,
  rade, turni e outlook, e ripubblica la dashboard.
- Il **tema** passa da solo a giorno/notte con l'alba e il tramonto.
- I **turni** ruotano da soli ogni giorno (skipper esenti).
- Fino all'8 agosto la dashboard gira in **SIMULAZIONE** (piano traslato a
  oggi); dall'8 agosto passa da sola alle date vere.

## Il giro dello skipper (5 minuti, due volte al giorno)

**La sera prima** (dopo il run delle 20:00):
1. Aprire la Plancia → guardare la tratta di domani, Sail Score, rada, gate
   notturna se 🌙.
2. **Controllare il bollettino del mare dell'Aeronautica** (link nel footer):
   prevale SEMPRE su Open-Meteo.
3. Se il piano va bene → **approvarlo dal telefono**: app GitHub → repo `nina`
   → Actions → "Aggiorna briefing" → Run workflow → campo `approva` = proprio
   nome → Run. Il banner della dashboard diventa verde per tutto l'equipaggio.

**La mattina**: ricontrollare bollettino + cielo reale. Il piano approvato
resta valido finché non cambia il giorno.

## Posizione reale (quando serve)

La posizione di default è quella **da piano**. Per dire alla Plancia dove
siamo davvero (meteo e mappe si ricentrano):

1. Google Maps → tenere premuto sulla propria posizione → copia coordinate.
2. App GitHub → Actions → Run workflow → incollare `lat`, `lon` e il nome del
   posto in `luogo` → Run.

La posizione GPS vale 24 ore, poi si torna a quella da piano (un dato vecchio
dichiarato è utile, uno vecchio spacciato per fresco no). La dashboard mostra
sempre la fonte: "(GPS, X h fa)" oppure "(da piano)".

> Nota: la condivisione posizione di Google Maps **non ha un'API ufficiale** —
> non si può leggere in automatico dall'account. Upgrade possibile in futuro:
> bot Telegram nel gruppo equipaggio (condividi posizione → la Plancia si
> aggiorna da sola). Richiede un token bot: da decidere.

## Parlare con l'agente (domande, cambi di piano)

Le domande vere — "e se domani andassimo a X?", "trova una rada riparata dal
Grecale", "rifai i conti" — si fanno a **Claude Code nella cartella del
progetto** (laptop, a casa o a bordo):

- `/briefing 2026-08-14` — briefing completo di una giornata
- `/rotta favone palombaggia 2026-08-19` — valuta una tratta e gli orari
- `/conti` — quote e conguaglio spese comuni
- `/cambusa 2026-08-15 2026-08-22` — lista spesa per l'intervallo
- `/approva Edo` — approvazione (equivalente al telefono)
- `/diario` — registrare la giornata nel logbook (serve anche alla
  calibrazione del modello, step 6)

Ogni modifica committata e pushata rideploya la dashboard in ~1 minuto.

## Ruoli e turni

- I turni giornalieri sono 6: cucina (pranzo/cena), pulizie (pranzo/cena),
  check barca (mattina/pomeriggio).
- Ogni membro ha in `voyage.json` il campo `duties`: la rotazione pesca solo
  chi ha quel ruolo (es. cucina solo chi sa cucinare). Gli skipper (Edo C,
  Bernardo B) sono sempre esenti.
- Per cambiare chi fa cosa: modificare `duties` in `data/voyage.json` e push
  (o chiederlo all'agente).

## Se qualcosa non torna

- Dashboard "vecchia": guardare "aggiornato X h fa" in alto a destra; se >12h,
  controllare Actions sul repo (i cron sui repo pubblici si disattivano dopo
  60 giorni senza commit — un run manuale li riattiva).
- Meteo strano: confrontare con il bollettino AM — vince lui, sempre.
- Dati `verify: true` (waypoint/rade): non usarli per decidere dove ancorare
  finché non sono verificati sul portolano (step 4).
- La polare è STIMATA: le velocità a vela valgono ±20% (step 5).
