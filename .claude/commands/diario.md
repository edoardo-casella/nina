---
description: Registra la giornata nel diario di bordo
---
Registra la giornata nel logbook seguendo `skills/logbook/SKILL.md`.
Chiedi (o deduci dal contesto) i dati duri — data, da/a, miglia, ore motore,
vento REALE osservato, mare, ancoraggio — e due righe di racconto, poi esegui
`python scripts/logbook.py add` con i parametri giusti. Il vento reale serve
anche alla calibrazione del modello ECMWF (step 6 del piano di avvio): sii
preciso su direzione e nodi. A fine crociera `python scripts/logbook.py render`
produce il diario in markdown.
