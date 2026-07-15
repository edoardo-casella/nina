# Contesto — crociera Corsica & La Maddalena 2026

Barca: **Dufour 48 Catamaran "Niña"** (2023), base Cannigione.
Periodo: 8 – 29 agosto 2026. Equipaggio 6–11 persone, cambi il 15 e il 22 agosto.
Notti in rada, salvo Cannigione (imbarco e cambi), Bonifacio, Bastia/San Fiorenzo.
Equipaggio in `voyage.json` con INIZIALI (repo pubblico): nomi completi, quote
charter e logistica voli solo in `data/Summer 26.xlsx` e
`data/crew-legend.local.md`, entrambi gitignorati.

## Regole non negoziabili

1. **Il piano lo approva lo skipper, mai l'agente.** Ogni output che assomiglia a una
   decisione ("si parte", "è sicuro", "vai tranquillo") è vietato. L'agente propone,
   spiega il perché, mostra il piano B.
2. **Il bollettino dell'Aeronautica Militare prevale su Open-Meteo.** Sempre. Se
   discordano, si dice all'utente che discordano.
3. **La rotta antioraria attorno alla Corsica è il default.** L'oraria solo con
   previsioni stabili confermate da due modelli con largo anticipo.
4. **Ogni dato con `verify: true` non è stato controllato su carta nautica.** Dirlo.
5. **Notturne solo su tratte flaggate `night` nel piano e SOLO con mare piatto**
   (onda ≤ `night_max_wave_m`, default 0.5 m, su tutto il transito). La dashboard
   mostra il gate; la decisione resta dello skipper la sera stessa. Nel piano
   2026 ce ne sono due: 18/8 Erbalunga→Favone e 20/8 Palombaggia→Porto Rotondo.
5. Documenti: dal 3 agosto 2026 la carta d'identità cartacea non vale per la Corsica.
   CIE o passaporto per tutti.

## Architettura

Stato unico: `data/voyage.json`. Otto skill in `skills/`, script in `scripts/`,
dashboard statica in `site/`, pubblicata da GitHub Actions due volte al giorno.

- `core.py` — stato, geodesia, polare (con VMG di bolina e di poppa)
- `weather.py` — Open-Meteo, cache 1 h, `ensemble_spread` per l'affidabilità;
  `daily_at`/`sea_daily` per il programma a 14 giorni (orizzonti troncati).
  Temperatura del mare (`sea_surface_temperature`) oraria + giornaliera →
  `briefing.now.sst` (posizione corrente) e `program.days[].sst` (per giorno,
  orizzonte marine ~8 gg poi `null`); modello, si aggiorna a ogni run
- `routing.py` — Sail Score, simulazione ora per ora
- `shelter.py` — Shelter Score per le rade
- `ledger.py` / `provisioning.py` / `logbook.py` / `import_kml.py`
- `draft_plan.py` — bozza one-off delle tappe giornaliere (dry-run di default)
- `photos.py` — foto destinazioni da Wikimedia Commons (`gallery_for` N foto /
  `photo_for` 1; geosearch, no API key, `_get` throttled+cache condiviso; mai bloccante)
- `enrich_destinations.py` — one-off: gallery + scheda Wikipedia per ogni
  destinazione votata → `data/destinations.json` (COMMITTATO). La CI non chiama
  mai Wikipedia/Commons: `publish.py` legge solo il file committato. Articolo
  scelto per match-nome + penalita' titoli-struttura (chiesa/stazione/faro);
  correzioni manuali nella mappa `OVERRIDES` (`--refresh --only <id>`)
- `publish.py` — genera i 4 JSON di `site/data/`: `briefing`, `weather`,
  `conti`, `program` (14 giorni con fascia di confidenza `piena`/`degradata`/`programma`)

### Giornata a tappe (`steps`)

Ogni giorno di `plan[]` può avere fino a 3 tappe in `steps[]`: chiavi
`slot` (mattina/pomeriggio/sera; "giornata" per tappa unica), `from`/`to`
(id waypoint, `from == to` = sosta), `depart_at`/`arrive_by` (HH:MM,
facoltativi), `activity` (bagno/trekking/bordo/porto/cambusa), `night_stay`
(esattamente 1 per i giorni normali, 0 nelle notturne), `verify`.
Vincoli: `steps[0].from == day.from`, `steps[-1].to == day.to`, catena
continua. I campi day-level `from/to/rest/night` restano l'autorità (il gate
notturna legge `night` lì). I giorni senza `steps` valgono come tappa unica.
Bozza: `python scripts/draft_plan.py` (dry-run) → revisione → `--write` → `git diff`.

La dashboard ha 4 viste hash-routed (`#oggi` executive summary + tappe,
`#vento` e `#mare` 48h + 14gg, `#programma` griglia 2 settimane). `sw.js`:
a ogni release del guscio si bumpa `SHELL`; la cache `DATA` non si rinomina mai.

## Stato dei dati

| File | Stato |
|---|---|
| `data/voyage.json` — crew e date | **REALI** (step 2, da Excel; iniziali). Diete: da raccogliere (default onnivoro) |
| `data/voyage.json` — conti | Charter €31.246 = autorità Excel, **fa fede il foglio Bonifici**; ledger.py gestisce solo le spese comuni (variable_budget da tarare) |
| `data/voyage.json` — plan | **REALE** 8–29 ago, 22 giorni antiorari (2 notturne, 2 soste). Tappe `steps`: bozza da `draft_plan.py`, **STIMATE** `verify: true` finché non riviste su carta |
| `data/voyage.json` — waypoints | **STIMATI** — coordinate approssimate, `verify: true` |
| `data/voyage.json` — waypoint `rating` | **STIMA agente** (1–5, bozza da guide/notorietà, 52 destinazioni; landmark esclusi) — voto estetico/esperienza, NON è lo Shelter Score; si conferma a bordo |
| `data/destinations.json` | **AUTO da Wikimedia** (gallery Commons + intro Wikipedia) via `enrich_destinations.py`; committato, la CI non lo rigenera. Rivedere gli articoli scelti (il matching nome può sbagliare) prima di fidarsi |
| `data/polars/dufour48cat.pol` | **STIMATA v2** (2026-07-10) — derated −17/−25% per crociera carica da fonti online (test GdV 2022 barca scarica, comparabili Lagoon 46/Elba 45/Bali 4.8, regole carico); attenti al MONOSCAFO Dufour 48 nei risultati web. Da validare a bordo (step 5) |
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

## Questionario equipaggio (Jotform) → profili sito

Form **261907242193053** "Questionario Equipaggio — Niña" (account Jotform di Edo).
Pipeline AUTORIZZATA da Edo (2026-07-15) a girare **in automatico, senza approvazione
per-profilo**: quando ci sono submission nuove l'agente pubblica direttamente.

1. `python scripts/jotform_profiles.py --check` / `--fetch` (richiede env `JOTFORM_API_KEY`,
   key full-access) → staging in `data/jotform-inbox/` (gitignored: email+allergie) + foto
   in `data/Profili/<crew_id>.jpg`. Stato in `data/jotform-processed.json` (committato).
2. L'agente scrive bio+epiteto (`data/crew-bios.json`), tag (`data/crew-tags.json`,
   FORMATO COMPATTO: array su una riga, editare a mano), nick (`NICKS` in build_crew.py)
   nel tono del sito (iniziali, affettuoso, vedi bio esistenti).
3. Foto: `python scripts/add_profile_photos.py` (ottimizza in site/crew/img/ e rilancia build_crew).
4. `python scripts/build_crew.py` → verifica render → commit + push (autorizzati per questa pipeline).

**Privacy (promessa nel form, NON negoziabile)**: mai pubblicare email, allergie/intolleranze,
preferenze cambusa/bibite, adesioni economiche (assicurazione/SUP). Pubblicabili: bio, ruoli,
aneddoti, nick, foto. Il blocco `riservati_non_pubblicare` dello staging resta fuori dal sito.
Il connettore MCP Jotform legge le submission (`api_request GET form/<id>/submissions`) ma non
scarica upload né cancella: per quello serve lo script con la key (env `JOTFORM_API_KEY`,
variabile utente Windows, salvata 2026-07-15).

**Foto profilo**: prima del push VERIFICARE VISIVAMENTE il ritratto (Read dell'immagine
ottimizzata) — è già successo che un membro caricasse la foto della colazione. Se non è un
ritratto: spostare in `data/jotform-inbox/` e segnalare a Edo.

**Scheda personale sul profilo**: `crew2026.q` in `site/data/crew.json` (overlay manuale
preservato da build_crew) con campi ruolo/esperienza/specialita/valigia/motto/funfact —
compilarla dal questionario (mai `dieta`, resta privata).

### Form aneddoti (registro di bordo) — Google Forms

**Piattaforma form: Google Forms per tutto il nuovo** (scelta di Edo 2026-07-15: i
connettori Google sono già autorizzati). Il questionario equipaggio resta su Jotform
(risposte già in corso + la Forms API non sa creare domande file-upload per la foto).

Form Google **"Aneddoti di bordo — Crewin"**, formId `1aa2DMLIC3rSznibC9rb4CPGnK1YZTdi6ZA2M7DznMMs`,
responder `https://docs.google.com/forms/d/e/1FAIpQLSdJ4TT9B_OmPnKZaKm436Eb8_QHQjx4zyaESe6drJyRHAeTjA/viewform`,
prefill `?usp=pp_url&entry.1120053238=<testo>`. CTA sul sito: `viaggio.html` ("C'eri anche
tu?...", prefill «Viaggio: nome — zona anno»), `membro.html` ("Racconta un aneddoto su X",
prefill «Membro: nome»), `aneddoti.html` ("Racconta il tuo").
Accesso API: OAuth (progetto OpenClaw-Vanessa), **refresh token in
`Desktop/Backupagent/gforms_token.json`** (scope forms.body + forms.responses.readonly) —
lettura risposte: `GET forms/<formId>/responses` senza nuovo consenso. In alternativa
collegare lo Sheet risposte e leggerlo col connettore Drive.
**Le submission aneddoti hanno GATE EDITORIALE — mai auto-publish** (espongono terzi):
l'agente prepara la bozza (anecdotes.json kind `leggenda` per storie non-skipper, o
arricchimento bio) e la sottopone a Edo prima di pubblicare. L'autorizzazione automatica
vale SOLO per i profili dal questionario equipaggio.

## Piano di avvio (PROMPT.md) — stato

Una cosa per volta, ogni passo confermato dallo skipper:

- [x] 1. Repository (2026-07-10): repo pubblico https://github.com/edoardo-casella/nina,
      Pages via Actions, dashboard https://edoardo-casella.github.io/nina/
      (pubblico perché il piano free non dà Pages sui privati: quando entreranno
      dati veri, valutare se togliere i conti dalla pagina)
- [x] 2. Equipaggio e conti (2026-07-10): 17 persone da `Summer 26.xlsx`,
      quadratura 181 persona-notte e occupazione giornaliera OK; charter fuori
      ledger (autorità Bonifici). Resta: diete reali
- [ ] 3. Waypoint: import KML da My Maps con `--merge`, punti rivisti uno a uno
- [ ] 4. Rade: verifica su portolano, togliere `verify: true` solo dopo
- [ ] 5. Polare: file reale dal cantiere o dal log NMEA
- [ ] 6. Calibrazione: briefing quotidiano + vento reale nel logbook da 2 settimane prima

Spuntare qui quando un passo è chiuso e aggiornare la tabella "Stato dei dati".
