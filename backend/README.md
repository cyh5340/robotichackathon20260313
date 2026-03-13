# MedGuard Backend

Backend services for MedGuard, organized by domain apps plus shared services/workers.

## Structure

- `apps/`: domain modules (auth, elders, medications, schedules, etc.)
- `services/`: cross-domain business services
- `workers/`: async/background jobs
- `api/`: API gateway/router composition
- `infra/`: deployment/runtime infrastructure definitions

This is a scaffold; implementation files should be added per domain.
