---
description: Marca il piano di oggi come approvato dallo skipper
---
Approva il briefing pubblicato: esegui `python scripts/publish.py --approve $1`
(se $1 manca, usa "Edo"). Prima di farlo mostra il piano corrente da
`site/data/briefing.json` (tratta, orario, rada, Sail Score) e chiedi conferma
esplicita: l'approvazione è la firma dello skipper sul piano, non un automatismo.
Ricorda che la dashboard pubblicata si aggiorna solo al prossimo run del workflow
o con un push.
