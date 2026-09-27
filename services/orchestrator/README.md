# Orchestrator

FastAPI checker for PreSearch. It downloads or reads the PDF, runs the paper stages, and stores conferences, claims, and chat in a local SQLite file. Keys stay in the environment. Never `NEXT_PUBLIC_`.

The chair-facing routes live under `/desk` and `/author`. The screen setup is in the [repository README](../../README.md).

## Start

From this directory, with the repo-root `.env` filled:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
set -a && source ../../.env && set +a
.venv/bin/uvicorn app:app --app-dir . --host 127.0.0.1 --port 8000
```

The default database is `playbook.sqlite` in this directory. It is gitignored. Do not point `RUN_DB` at `/tmp` if the lists should survive a restart.

## Health

```bash
curl -s http://127.0.0.1:8000/health
```

## Tests

```bash
.venv/bin/pytest
```

## Playbook loop

`POST /runs`, `GET /runs/{id}`, `POST /runs/{id}/replay`, and `GET /playbook` are the scored patch loop. A chair does not run that loop from the desk. A patch that lowers fitness is archived. Agents do not edit this service’s source to make a run pass.
