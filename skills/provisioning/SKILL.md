---
name: provisioning
description: Genera la lista della cambusa per una tratta, scalata sulle persone effettivamente a bordo giorno per giorno e sulle loro diete, con budget stimato. USA QUESTA SKILL ogni volta che si parla di cambusa, spesa, provviste, "cosa compriamo", quanta acqua, quanto cibo, supermercato, o quando cambia l'equipaggio e va rifatta la spesa.
---

# Provisioning (cambusa)

I consumi sono in unita' per **persona-giorno** (`RATES` in `scripts/provisioning.py`). Lo script conta quante persone sono a bordo ogni singolo giorno dell'intervallo, sottrae le voci escluse per dieta, e aggiunge il 10% di margine.

## Comando

```bash
python scripts/provisioning.py 2026-08-09 2026-08-17
```

Output: persona-giorno totali, ripartizione per dieta, quantita' per voce, budget.

## Regole di cambusa

1. **Acqua**: 3 L/persona/giorno *anche con il dissalatore*. I dissalatori si guastano, e si guastano sempre nel giorno peggiore. `RATES` conta 1.5 L di bottiglia da bere; l'altra meta' viene dai serbatoi. Prevedere comunque una riserva d'emergenza separata.
2. **Fare la spesa grossa prima della tratta piu' lunga**, non prima di quella piu' comoda.
3. Il ghiaccio si consuma il doppio di quanto si pensi, in agosto.
4. Le diete vanno lette da `crew[].diet`: se cambia l'equipaggio a meta' viaggio cambia la lista, non solo le quantita'.
5. Le voci in grammi e millilitri vanno tradotte in **confezioni reali** prima di andare al supermercato. Farlo nella risposta, non lasciarlo all'utente.

## Dopo la spesa

Registrare l'importo effettivo in `expenses[]` con `beneficiaries: "aboard"`, poi passare a `crew-ledger` per il conguaglio.
