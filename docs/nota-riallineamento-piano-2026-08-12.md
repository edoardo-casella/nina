# Nota per lo skipper — piano vs realtà (12/08/2026)

**Non applicata: il piano è tuo.** Proposta di riallineamento minimo di
`data/voyage.json.plan`, da fare quando hai 5 minuti.

## Il disallineamento

La barca è ~1 giorno avanti sul piano:

| Data | Piano nel repo | Realtà (diario) |
|---|---|---|
| 11/08 | bonifacio → tizzano | Isola Piana → Bonifacio → **Roccapina** |
| 12/08 | tizzano → campomoro | Roccapina → **Golfo di Ajaccio** |
| 13/08 | campomoro → isolella | — |

Finché resta così: `leg_for` serve la tratta sbagliata, il ranking "stanotte"
punta alla rada sbagliata, e se la posizione GPS invecchia oltre 24 h la
Plancia torna alla posizione da piano (= Tizzano). Con il bot Telegram attivo
il danno è mitigato (meteo/mappe seguono il GPS), ma piano e outlook restano
storti.

## Riallineamento minimo proposto (conserva tutte le date successive)

1. **12/08**: `from: cr_roccapina_nord`, `to: isolella` (o `ajaccio`)
2. **13/08**: giornata locale nel Golfo — `isolella → isolella`
   (opzionale una tappa `sanguinaires`, il waypoint esiste)
3. **dal 14/08** (`isolella → girolata` e seguenti): invariato

Un edit, un `git diff` leggibile, poi il normale giro di approvazione.
