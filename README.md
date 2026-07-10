# sailing-agent — Niña, Corsica & La Maddalena 2026

Agente di pianificazione per crociere a vela, per Claude Code.
Otto skill che ruotano attorno a un unico file di stato: `data/voyage.json`.

> **Questa copia è già installata** in `35_SailingAgent` (2026-07-10), verificata
> su Windows e adattata: I/O UTF-8, cache meteo portabile con chiave stabile,
> comandi slash in `.claude/commands/` e subagent `meteo-analyst` /
> `rada-verifier` in `.claude/agents/`. I dati sono ancora FITTIZI: il piano di
> sostituzione è in `PROMPT.md`, lo stato passo-passo in `CLAUDE.md`.

## Installazione

```bash
# 1. copia la cartella nel progetto
cp -r sailing-agent ~/.claude/plugins/     # oppure nella root del progetto

# 2. meteo via MCP (opzionale ma consigliato per le domande in linguaggio naturale)
claude mcp add weather -- npx -y @dangahagan/weather-mcp@latest

# 3. gli script girano con Python 3.10+ senza dipendenze esterne
python scripts/core.py     # verifica che tutto carichi
```

## Le otto skill

| Skill | Fa questo |
|---|---|
| `weather-router` | Sail Score 0-100, simulazione ora per ora, orario di partenza migliore |
| `anchorage-scout` | Shelter Score, semaforo verde/giallo/rosso per ogni rada |
| `daily-briefing` | Orchestra tutte le altre e produce il briefing del giorno |
| `crew-ledger` | Quote per persona-notte, conguaglio con bonifici minimi |
| `provisioning` | Cambusa scalata su persone a bordo e diete |
| `crew-survey` | Questionario preferenze -> vincoli di pianificazione |
| `waypoint-db` | Import KML da Google My Maps, distanze, rotte |
| `logbook` | Diario di bordo, dati duri + racconto |

## Comandi slash

`/briefing 2026-08-12` · `/rotta cannigione spargi 2026-08-12` · `/conti`

## Cosa sostituire prima di usarlo davvero

I dati sono **fittizi**. In ordine di importanza:

1. **`data/voyage.json`** — equipaggio reale con date di imbarco/sbarco, costi reali dal tuo Excel, waypoint reali.
2. **`data/polars/dufour48cat.pol`** — la polare e' una stima. Chiedi il file al cantiere o costruiscilo a bordo dal log NMEA. Il router e' preciso quanto la polare.
3. **`data/anchorages.json`** — i settori esposti sono stimati a occhio. Vanno verificati sul portolano (Imray *Italian Waters Pilot*, Navicarte). Ogni voce ha `verify: true` finche' non l'hai controllata.
4. **`RATES` in `scripts/provisioning.py`** — i consumi dipendono dal gruppo.

## Import dell'Excel dei conti

Non c'e' un parser automatico: le strutture degli Excel sono tutte diverse.
Apri il tuo file, poi chiedi a Claude di mappare le colonne su `costs.fixed`,
`costs.variable_budget` e `expenses[]` in `voyage.json`. Una volta sola.

## Limiti da tenere a mente

- **`haversine_nm` non evita la terraferma.** Tratte che aggirano capi vanno spezzate in gambe.
- **I modelli d'onda hanno risoluzione ~5 km.** Sottocosta sono indicativi.
- **Open-Meteo non e' un servizio ufficiale.** Il bollettino del mare dell'Aeronautica Militare (meteoam.it/it/mare) prevale sempre.
- Il Sail Score e' un suggerimento. Decide lo skipper, e nessun software si assume la responsabilita' di una decisione in mare.

## Dashboard

Sito statico in `site/`, pubblicato su GitHub Pages da `.github/workflows/update.yml`
(cron 10:00 e 18:00 UTC = 12:00 e 20:00 ora italiana, più il bottone "Run workflow").

```bash
python scripts/publish.py --offline        # genera i JSON con vento sintetico
python -m http.server -d site 8000         # prova in locale
python scripts/publish.py --approve Edo    # marca il piano di oggi come approvato
```

**Il meteo si aggiorna da solo. Il piano no.** Ogni briefing nasce
`"approved": false` e la pagina lo dichiara in magenta. Un algoritmo che genera un
piano e lo mostra a nove persone come fatto compiuto è il modo in cui si finisce
sottovento con trenta nodi perché "lo diceva il sito". Se il giorno non è cambiato,
il workflow conserva l'approvazione precedente invece di cancellarla.

Offline: service worker con cache dei dati. In rada senza rete la pagina si apre
e mostra l'ultimo briefing scaricato **con la sua età in evidenza**. Un dato vecchio
dichiarato è utile; un dato vecchio spacciato per fresco è pericoloso.

Design: convenzioni della carta nautica IIM. Magenta per gli avvisi, tinte di
batimetria per gli sfondi, corsivo per ciò che riguarda l'acqua e tondo per la terra.
