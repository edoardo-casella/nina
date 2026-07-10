# Contesto — crociera Corsica & La Maddalena 2026

Barca: **Dufour 48 Catamaran "Niña"** (2023), base Cannigione.
Periodo: 9 – 29 agosto 2026. Equipaggio 8-10 persone, due cambi (17 e 22 agosto).
Ancoraggio ogni notte, nessun porto.

## Regole non negoziabili

1. **Il piano lo approva lo skipper, mai l'agente.** Ogni output che assomiglia a una
   decisione ("si parte", "è sicuro", "vai tranquillo") è vietato. L'agente propone,
   spiega il perché, mostra il piano B.
2. **Il bollettino dell'Aeronautica Militare prevale su Open-Meteo.** Sempre. Se
   discordano, si dice all'utente che discordano.
3. **La rotta antioraria attorno alla Corsica è il default.** L'oraria solo con
   previsioni stabili confermate da due modelli con largo anticipo.
4. **Ogni dato con `verify: true` non è stato controllato su carta nautica.** Dirlo.
5. Documenti: dal 3 agosto 2026 la carta d'identità cartacea non vale per la Corsica.
   CIE o passaporto per tutti.

## Architettura

Stato unico: `data/voyage.json`. Otto skill in `skills/`, script in `scripts/`,
dashboard statica in `site/`, pubblicata da GitHub Actions due volte al giorno.

- `core.py` — stato, geodesia, polare (con VMG di bolina e di poppa)
- `weather.py` — Open-Meteo, cache 1 h, `ensemble_spread` per l'affidabilità
- `routing.py` — Sail Score, simulazione ora per ora
- `shelter.py` — Shelter Score per le rade
- `ledger.py` / `provisioning.py` / `logbook.py` / `import_kml.py`
- `publish.py` — genera `site/data/*.json`

## Stato dei dati

| File | Stato |
|---|---|
| `data/voyage.json` | **FITTIZIO** — equipaggio, costi e piano inventati |
| `data/polars/dufour48cat.pol` | **STIMATA** — non è la polare reale della barca |
| `data/anchorages.json` | **STIMATO** — settori esposti a occhio, da portolano |
| `RATES` in `provisioning.py` | da tarare sul gruppo |

Quando sostituisci un dato, togli `verify: true` e aggiorna questa tabella.

## Convenzioni

- Italiano, risposte sintetiche.
- Le miglia sono nautiche, il vento in nodi, le direzioni in gradi veri.
- `haversine_nm` **non evita la terraferma**: tratte che aggirano capi vanno spezzate.

## Installazione in questo workspace (35_SailingAgent)

Progetto personal-lane del command center `99_AI_Workspace` (mailbox disabilitata).
Installato e verificato il 2026-07-10; tutti gli script girano su Windows
(Python 3.13, `PYTHONUTF8=1` impostato in `.claude/settings.json`).

- Comandi slash: `/briefing`, `/rotta`, `/conti`, `/cambusa`, `/approva`, `/diario`
  (in `.claude/commands/`; `commands/` in root è il layout plugin originale).
- Subagent: `meteo-analyst` (quadro meteo + cross-check bollettino AM),
  `rada-verifier` (schede di verifica per `anchorages.json` — propone, non scrive).
- Le skill in `skills/` sono playbook da leggere e seguire, non skill registrate
  nell'harness.
- Fix applicati al kit originale: I/O sempre `encoding="utf-8"`, cache meteo in
  `tempfile.gettempdir()` con chiave `sha1` stabile (prima usava `hash()`
  randomizzato: cache mai riusata), stdout riconfigurato UTF-8 per console Windows.

## Piano di avvio (PROMPT.md) — stato

Una cosa per volta, ogni passo confermato dallo skipper:

- [x] 1. Repository (2026-07-10): repo pubblico https://github.com/edoardo-casella/nina,
      Pages via Actions, dashboard https://edoardo-casella.github.io/nina/
      (pubblico perché il piano free non dà Pages sui privati: quando entreranno
      dati veri, valutare se togliere i conti dalla pagina)
- [ ] 2. Equipaggio e conti: mappare l'Excel reale su `voyage.json`
- [ ] 3. Waypoint: import KML da My Maps con `--merge`, punti rivisti uno a uno
- [ ] 4. Rade: verifica su portolano, togliere `verify: true` solo dopo
- [ ] 5. Polare: file reale dal cantiere o dal log NMEA
- [ ] 6. Calibrazione: briefing quotidiano + vento reale nel logbook da 2 settimane prima

Spuntare qui quando un passo è chiuso e aggiornare la tabella "Stato dei dati".
