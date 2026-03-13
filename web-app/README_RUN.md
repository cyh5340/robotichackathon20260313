# MedGuard Web App: Quick Start

## 1) Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SMALLEST_API_KEY="your_smallest_api_key"
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Verify: open http://localhost:8000/health should return `{"status":"ok",...}`.

## 2) Frontend

```bash
cd web-app
npm install
npm run dev
```

Open http://localhost:3000. The Dashboard will show:

- Backend Health: ok
- Recent Notification Events: No realtime events yet
- Voice Instruction (Smallest.ai): Start recording / Stop recording

## 3) Test a round-trip

In another terminal:

```bash
curl -X POST http://localhost:8000/elders \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Alice"}'
```

Then on the web dashboard, refresh or navigate to /elders to see the API is reachable through the service stubs.

## 4) Realtime events

The dashboard client connects to ws://localhost:8000/ws/events.

To produce realtime events quickly:

1. Create an adherence log with status `taken`, `missed`, `skipped`, or `held_unsafe`.
2. Or create/update a robot task and set status to `completed` / `failed`.

Those events will appear in Dashboard and Alerts.

## 5) Voice instruction transcription

The dashboard includes a **Voice Instruction (Smallest.ai)** card:

1. Click **Start recording** and speak a command.
2. Click **Stop recording**.
3. The transcribed instruction appears under **Instruction**.

Backend endpoint used: `POST /voice/instruction` (multipart audio upload).

## 6) User onboarding process

Go to `/onboarding` in the web app and submit:

1. Basic user information (name, DOB, phone, email, address)
2. Doctor details (doctor name and contact)
3. Doctor's orders file upload (PDF/image/text)

Backend endpoints used:

- `POST /onboarding` (multipart form + doctor's orders file)
- `GET /onboarding` (list submitted onboarding records)

## Stopping

- Frontend: Ctrl+C in the `npm run dev` terminal
- Backend: Ctrl+C in the `uvicorn` terminal; then `deactivate` the venv

That’s the minimal two-service local loop for MedGuard web.
