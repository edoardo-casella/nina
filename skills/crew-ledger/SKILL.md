---
name: crew-ledger
description: Calcola le quote di ogni membro dell'equipaggio con imbarchi e sbarchi scaglionati, usando l'unita' persona-notte, e produce il conguaglio finale (chi deve quanto a chi). USA QUESTA SKILL ogni volta che si parla di quote, conti, "quanto paga ognuno", "chi ha anticipato", "come dividiamo", cambi equipaggio, split delle spese, o quando qualcuno sale o scende dalla barca a meta' vacanza.
---

# Crew Ledger

**L'unita' di conto e' la persona-notte.** Chi dorme una notte in barca paga una notte. Chi resta 20 notti paga il doppio di chi ne resta 10. Questa e' la sola divisione difendibile quando l'equipaggio ruota.

## Due tipi di costo

- `split: "person_nights"` — charter, pulizie, cauzione, transit log. Si spalmano su tutte le persona-notte.
- `split: "equal"` — voci che restano a tutti allo stesso modo (es. i SUP acquistati). Divisione in parti uguali.

Le voci variabili (`variable_budget`) sono in EUR per persona-giorno: cambusa, gasolio, ormeggi, extra.

## Comandi

```bash
python scripts/ledger.py quote         # tabella quote per persona
python scripts/ledger.py conguaglio    # bonifici minimi per pareggiare
python scripts/ledger.py occupazione   # istogramma persone a bordo per giorno
```

## Conguaglio

`settle()` legge `expenses[]`, calcola chi ha anticipato e chi ha beneficiato, e riduce tutto al **numero minimo di bonifici**. Il campo `beneficiaries` puo' essere `"aboard"` (chi era a bordo quel giorno — il caso normale per la cambusa) o una lista esplicita di id.

Registrare una spesa significa aggiungere un oggetto a `expenses[]` in `data/voyage.json`. Farlo lo stesso giorno: a fine viaggio nessuno ricorda chi ha pagato il gasolio a Bonifacio.

## Come rispondere

- Mostrare sempre le persona-notte totali: e' il denominatore, chiarisce tutto.
- Distinguere **preventivo** (quote da `variable_budget`) da **consuntivo** (spese reali da `expenses[]`). Non mescolarli.
- Se il totale a persona cambia con l'headcount, dirlo esplicitamente: due persone in meno spostano le quote di tutti.
- Non arrotondare al ribasso per far quadrare. Mostrare i centesimi nel conguaglio.
