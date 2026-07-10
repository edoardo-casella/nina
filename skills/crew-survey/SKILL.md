---
name: crew-survey
description: Costruisce e analizza il questionario di preferenze dell'equipaggio (ritmi, cucina, mal di mare, tolleranza alla navigazione, budget), e traduce le risposte in vincoli di pianificazione. USA QUESTA SKILL quando si parla di preferenze dell'equipaggio, questionario, sondaggio, "cosa vogliono gli altri", comfort a bordo, mal di mare, o prima di fissare il ritmo del viaggio con un gruppo nuovo.
---

# Crew Survey

Un viaggio confortevole non e' quello con la rotta migliore, e' quello che **non forza nessuno oltre la sua soglia**. Il questionario esiste per scoprire quelle soglie prima di partire, non a bordo.

## Le domande che contano

Sette, non venti. Nessuno compila venti domande.

1. **Mal di mare**: mai / a volte / spesso / non lo so → determina `max_wave_comfort_m` e se si naviga di bolina
2. **Ore di navigazione al giorno tollerate**: 2 / 4 / 6+ → determina `max_daily_nm`
3. **Sveglia**: alba / 8-9 / il piu' tardi possibile → determina `earliest_departure`
4. **Cosa cerchi**: relax e nuotate / vela vera / esplorare posti / vita sociale a terra
5. **Cucina**: cucino volentieri / do una mano / preferisco pulire
6. **Budget extra oltre la quota**: fascia
7. **Diete e allergie**: testo libero → alimenta `crew[].diet`

## Somministrazione

Se il connettore **Jotform** e' disponibile, creare il modulo li' e raccogliere le risposte. Altrimenti generare un Google Form o un semplice markdown da incollare in chat di gruppo. Non costruire un'app: nessuno la aprira'.

## Dalle risposte ai vincoli

Aggiornare `preferences` in `data/voyage.json`. La regola e' **il minimo comune, non la media**:
- `max_wave_comfort_m` = quello della persona piu' sensibile a bordo *in quel momento*
- `max_daily_nm` = il minimo dichiarato dal gruppo presente
- Se una sola persona soffre il mal di mare, la bolina lunga si evita: costa a lei molto piu' di quanto renda agli altri

Le preferenze **cambiano a ogni cambio equipaggio**. Ricalcolarle usando `core.aboard_on(v, giorno)`.

## Cautela

Le risposte a un questionario sono dichiarazioni, non fatti. Chi scrive "vela vera" a marzo puo' voler stare in rada ad agosto. Chiedere di nuovo a bordo, il secondo giorno.
