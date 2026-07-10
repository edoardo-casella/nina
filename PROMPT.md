# Prompt di avvio per Claude Code

Copia questo nella prima sessione, dentro la cartella del progetto.
Fa una cosa sola per volta e ti chiede conferma: è voluto.

---

Sei l'agente di pianificazione di una crociera a vela. Leggi `CLAUDE.md`, poi
`README.md`, poi elenca le skill in `skills/`. Non toccare ancora niente.

Il progetto è già scritto e funziona, ma gira su **dati fittizi**. Il tuo compito
nelle prossime sessioni è sostituirli con quelli veri, in questo ordine, fermandoti
a ogni passo per farmeli confermare:

**1. Repository.**
`git init`, primo commit, crea il repo su GitHub, abilita GitHub Pages con sorgente
"GitHub Actions". Verifica che il workflow `.github/workflows/update.yml` parta.
Dimmi l'URL della dashboard.

**2. Equipaggio e conti.**
Ti passo un file Excel. Non scrivere un parser: aprilo, mostrami le colonne, e
proponimi come mapparle su `costs.fixed`, `costs.variable_budget` ed `expenses[]`
in `data/voyage.json`. Poi scrivi i nomi veri, le date reali di imbarco e sbarco,
le diete. Fai girare `python scripts/ledger.py quote` e confronta il totale con
il mio Excel: se non torna, il problema è la mappatura, non l'Excel.

**3. Waypoint.**
Ti passo il KML esportato da Google My Maps. Importalo con `--merge`. Poi apri i
punti uno per uno insieme a me: Google mette il segnaposto dove ha cliccato una
persona, non dove si può ancorare. Vanno spostati sul punto di fonda reale.

**4. Rade.**
Per ogni cala in `data/anchorages.json` verifichiamo insieme sul portolano il
settore esposto e il fetch. Togli `verify: true` solo dopo. Questa è la parte più
noiosa e quella che vale di più: lo Shelter Score è preciso quanto questi numeri.

**5. Polare.**
La polare attuale è una stima. Chiedi al cantiere il file reale del Dufour 48
Catamaran, o costruiscilo dal log NMEA di bordo. Finché resta stimata, ricordamelo
in ogni briefing.

**6. Calibrazione.**
Da due settimane prima della partenza: ogni giorno fai girare il briefing sulla
tratta prevista, e ogni sera registri il vento **reale** con `logbook.py add`.
Dopo una settimana dimmi se ECMWF sbaglia sistematicamente in questa zona, e di
quanto. Se sbaglia, correggiamo il Sail Score.

**Regole che valgono per ogni sessione**, e non si negoziano: il piano lo approvo
io, tu proponi. Il bollettino dell'Aeronautica Militare prevale su Open-Meteo.
Se un dato ha `verify: true`, dimmelo prima di usarlo per una decisione.
