---
name: daily-briefing
description: Produce il briefing del giorno per l'equipaggio, mettendo insieme meteo, Sail Score della tratta, scelta della rada, orari, turni e piano B. USA QUESTA SKILL ogni mattina o la sera prima, e ogni volta che si chiede "cosa facciamo domani", "il programma di oggi", "briefing", "piano della giornata", "dove andiamo", "a che ora si parte". E' la skill che orchestra tutte le altre.
---

# Daily Briefing

E' l'orchestratore. Chiama nell'ordine: `weather-router` → `anchorage-scout` → `provisioning` (se serve spesa) → `logbook` (per registrare a fine giornata).

## Struttura del briefing

Sei blocchi, in quest'ordine. Mai piu' di una pagina: nessuno legge un briefing lungo prima di colazione.

1. **Meteo** — vento e onda attesi, con l'affidabilita' dei modelli. Una riga sul bollettino AM.
2. **Tratta** — da/a, miglia, rotta, orario di partenza consigliato, ETA, Sail Score, percentuale a vela. Se il punteggio e' basso, dire *perche'*: bolina, calma, onda.
3. **Rada** — dove si dorme, semaforo, e il **piano B** raggiungibile in meno di un'ora.
4. **Orari** — sveglia, salpa ancora, sosta bagno, ancoraggio (mai oltre `latest_anchor_time`).
5. **Equipaggio** — chi e' a bordo oggi (`core.aboard_on`), turni cucina, chi ha il tender. Segnalare i cambi equipaggio con **due giorni** di anticipo, non il giorno stesso.
6. **Note** — cambusa da fare, acqua, gasolio, cose da comprare a terra.

## Priorita' quando i fattori confliggono

Nell'ordine, e non e' negoziabile:

1. **Sicurezza** — vento oltre soglia, rada esposta, temporali: si resta fermi. Un giorno perso e' un giorno perso; una barca sull'ancora che ara di notte e' un'altra cosa.
2. **Comfort dell'equipaggio** — se a bordo c'e' chi soffre il mare, 4 ore di bolina distruggono tre giorni di vacanza. Il Sail Score alto non vale se meta' equipaggio sta male.
3. **Vincoli logistici** — traghetti dei cambi equipaggio, orari di rientro alla base, supermercati chiusi la domenica.
4. **Bellezza della navigazione** — qui, e solo qui, si ottimizza il Sail Score.

Un traverso a 15 nodi con 0.5 m di onda vale piu' di qualunque itinerario perfetto sulla carta.

## Regole

- La rotta di default e' **antioraria** attorno alla Corsica: e' la piu' sicura con il Maestrale. Oraria solo con previsioni stabili confermate da due modelli con largo anticipo.
- Se `ensemble_spread` da affidabilita' bassa, **non pianificare oltre le 24 h**. Dirlo all'equipaggio invece di far finta di sapere.
- Il briefing propone. Lo skipper decide. Non usare mai formule come "puoi partire" o "e' sicuro".
- A fine giornata, registrare tutto con `logbook`.
