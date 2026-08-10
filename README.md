# Flow

Un moniteur minimal de flux d’événements. Il valide chaque événement JSON Lines et enregistre les alertes utiles.

## Ce qui fonctionne

- validation des champs obligatoires ;
- alertes de latence supérieure à 2 secondes ;
- alertes sur montant inhabituel ;
- persistance dans `out/alerts.jsonl`.

```bash
cd projects/flow
python3 src/monitor.py
```

Suite : Kafka, fenêtre statistique et notifications opérationnelles.
