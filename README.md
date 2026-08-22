# Flow

Flow est un moniteur d’événements utilisable localement. Il accepte un événement JSON via HTTP, applique des règles de surveillance et expose les métriques et alertes dans une interface web.

## Démarrer l’application

```bash
python3 src/server.py
```

Ouvrir `http://127.0.0.1:8000`, puis envoyer un événement depuis l’interface ou l’API.

## API

```bash
curl -X POST http://127.0.0.1:8000/api/events \
  -H 'Content-Type: application/json' \
  -d '{"event_id":"evt-01","amount":42.5,"latency_ms":180,"type":"order_created"}'

curl http://127.0.0.1:8000/api/metrics
curl http://127.0.0.1:8000/api/alerts
```

## Flux public de démonstration

L’interface peut également écouter, directement depuis le navigateur, le flux public `BTCUSDT@aggTrade` de Binance Spot. L’utilisateur choisit ensuite s’il souhaite injecter un événement observé dans Flow. Cette intégration ne passe aucun ordre et ne constitue pas un conseil financier : elle sert uniquement à travailler un événement réel, sa provenance et sa latence.

## Règles intégrées

- champs requis : `event_id`, `amount`, `latency_ms`, `type` ;
- alerte de latence au-delà de 2 000 ms ;
- alerte de montant au-delà de 10 000.

`src/monitor.py` reste disponible pour traiter le fichier de démonstration en batch.

## Docker et Render

```bash
docker build -t flow .
docker run --rm -p 8000:8000 flow
```

`render.yaml` permet de créer un Blueprint sur Render pour mettre l’application en ligne.

## Vérifier

```bash
python3 -m unittest discover -s tests
```
