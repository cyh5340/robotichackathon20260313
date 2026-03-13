# FastAPI Starter

Minimal runnable backend starter for MedGuard.

## Files

- `backend/main.py`: FastAPI app with starter endpoints
- `backend/openapi.yaml`: minimal OpenAPI spec
- `backend/requirements.txt`: runtime dependencies

## Run

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

## Starter Endpoints

- `GET /health`
- `POST /voice/instruction`
- `POST /onboarding`
- `GET /onboarding`
- `POST /elders`
- `GET /elders/{elder_id}`
- `POST /elders/{elder_id}/medications`
- `GET /elders/{elder_id}/medications`
- `POST /adherence/logs`
- `GET /elders/{elder_id}/adherence`
- `POST /robot/tasks`
- `GET /robot/tasks/{task_id}`

## Notes

This starter uses in-memory dictionaries for speed of prototyping.
Replace with persistent storage (PostgreSQL + migrations) for real workflows.
