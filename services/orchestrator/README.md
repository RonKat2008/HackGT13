# Orchestrator

Venv is already at `services/orchestrator/.venv`.

Keys stay in the environment (`XAI_API_KEY`, `OPENROUTER_API_KEY`). Never `NEXT_PUBLIC_`.

## Start

```bash
cd services/orchestrator
RUN_DB=/tmp/hackgt-o13.sqlite .venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
```

## Health

```bash
curl -s http://127.0.0.1:8000/health
```

## Create a fixture run

```bash
curl -s -X POST http://127.0.0.1:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{"product":"stormcite","goal":"Check the metric in the results","fixture":true}'
```

## Get a run

```bash
curl -s http://127.0.0.1:8000/runs/{id}
```

## Replay a run

```bash
curl -s -X POST http://127.0.0.1:8000/runs/{id}/replay
```

## Live playbook

```bash
curl -s 'http://127.0.0.1:8000/playbook?product=stormcite'
```
