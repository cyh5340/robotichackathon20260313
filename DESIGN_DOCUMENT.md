# Design Document — MedGuard: AI-Assisted Robotic Medication Management System

**Version:** 2.0
**Date:** 2026-03-13
**Status:** Current

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Module Specifications](#3-module-specifications)
4. [Backend API Reference](#4-backend-api-reference)
5. [Data Flow](#5-data-flow)
6. [API & SDK Integrations](#6-api--sdk-integrations)
7. [Inverse Kinematics — Mathematical Model](#7-inverse-kinematics--mathematical-model)
8. [Configuration & Environment Variables](#8-configuration--environment-variables)
9. [Dependencies](#9-dependencies)
10. [Known Limitations & Future Work](#10-known-limitations--future-work)
11. [Setup & Running](#11-setup--running)

---

## 1. Executive Summary

MedGuard is a **robotic medication management system** for elder care. A caregiver or operator interacts through a web dashboard or voice interface; a Cyberwave **SO-101** 6-DOF robotic arm physically picks, sorts, and delivers medications. An AI pipeline handles object classification, visual detection, and compliance logging.

### System Components

| Component | Technology | Port |
|---|---|---|
| Web dashboard | Next.js 14 (React) | 3000 |
| REST + WebSocket backend | FastAPI + Uvicorn | 8000 |
| Robot arm | Cyberwave SO-101 via lerobot | USB serial |
| STT / TTS | Smallest.ai | — |
| Object detection | Featherless.ai VLM | — |
| Fragility classification | Featherless.ai LLM | — |
| Fragility TTS warning | ElevenLabs | — |
| Skill middleware | Toolhouse | — |
| Orchestration LLM | Anthropic Claude Sonnet 4.6 | — |

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Next.js Web App (:3000)                      │
│                                                                 │
│  /              Dashboard (live alerts, health)                 │
│  /elders        Elder management                                │
│  /medications   Medication records per elder                    │
│  /adherence     Dose log & compliance tracking                  │
│  /alerts        Real-time notification feed                     │
│  /onboarding    New patient intake + doctor's orders upload     │
│  /robot         SO-101 task console                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP + WebSocket
┌──────────────────────────▼──────────────────────────────────────┐
│                   FastAPI Backend (:8000)                       │
│                                                                 │
│  REST endpoints (elders, medications, adherence, alerts,        │
│                  onboarding, robot/tasks, voice, vision)        │
│  WebSocket  /ws/events  — broadcasts NotificationEvents         │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              Robot Execution Layer                     │    │
│  │                                                        │    │
│  │  pick_and_place.py   ─── Featherless LLM (fragility)  │    │
│  │       │              ─── ElevenLabs TTS (warning)      │    │
│  │       │              ─── Toolhouse / Google Sheets     │    │
│  │  vision.py           ─── Featherless VLM (detection)  │    │
│  │  arm_control.py      ─── lerobot → SO-101 hardware    │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### Layer Summary

| Layer | Files | Responsibility |
|---|---|---|
| **Presentation** | `web-app/src/app/**` | User-facing pages, forms, real-time alert feed |
| **API** | `backend/main.py` | REST CRUD, WebSocket event bus, background task runner |
| **Robot control** | `arm_control.py` | IK solver, joint-angle commands, gripper |
| **Vision** | `vision.py` | VLM-based object detection from camera images |
| **Fragility pipeline** | `pick_and_place.py` | LLM classification, ElevenLabs TTS, torque-limited pick |
| **Voice I/O** | `listener.py` | Mic STT and speaker TTS via Smallest.ai |
| **Orchestrator** | `main.py` (root) | Standalone voice-command loop (alternative entry point) |

---

## 3. Module Specifications

### 3.1 `backend/main.py` — FastAPI Application

The backend is the integration hub. On startup it:
1. Loads `.env` from the repo root via `python-dotenv`
2. Adds the repo root to `sys.path` so robot modules are importable
3. Hard-imports `pick_and_place`, `vision`, and `arm_control` — no fallbacks

When `POST /robot/tasks` receives a `pick_and_place` task it immediately launches `_run_robot_task()` as an `asyncio` background task. The robot pipeline runs in a thread pool (`loop.run_in_executor`) so the event loop stays unblocked. Status transitions (`queued → running → completed/failed`) are broadcast over `/ws/events` as `NotificationEvent` payloads.

---

### 3.2 `listener.py` — `AudioInterface`

**Purpose:** Capture spoken operator commands and deliver auditory feedback.

| Method | Signature | Description |
|---|---|---|
| `listen` | `() -> str` | Records mic until 1.5 s silence, encodes WAV, calls STT |
| `speak` | `(text: str) -> None` | Synthesises text via Waves Lightning, plays via PyAudio |

#### STT Pipeline

```
Microphone (16 kHz, mono, PCM 16-bit)
  -> PyAudio stream (1024-sample chunks)
  -> RMS silence detection (threshold: 500 amplitude units)
  -> Stop after 1.5 s silence OR 15 s hard cap
  -> Pack frames into in-memory WAV
  -> POST to Smallest.ai speech_to_text.transcribe()
  -> Return transcript string
```

#### TTS Pipeline

```
Text string
  -> Smallest.ai tts.synthesize()  [Waves Lightning, voice: emily, 24 kHz]
  -> Raw audio bytes (WAV or PCM)
  -> PyAudio output stream
```

---

### 3.3 `vision.py` — `RobotVision`

**Purpose:** Locate a named object in a camera image and return its pixel centre.

| Method | Signature | Description |
|---|---|---|
| `detect_object` | `(command: str, image_path: str) -> tuple[int, int]` | Sends image + text to VLM, returns `(X, Y)` pixel coords |

#### Detection Pipeline

```
image_path
  -> base-64 encode (JPEG / PNG auto-detected)
  -> Featherless.ai chat completion (Qwen2.5-VL-72B-Instruct)
       System prompt: "Return COORDS: X=<int> Y=<int> only"
       User content:  base-64 image data-URL + target description
  -> regex parse: r"X\s*=\s*(\d+)\s+Y\s*=\s*(\d+)"
  -> return (x, y)
```

Also exposed via the backend as `POST /robot/vision/detect` (multipart: `target` + `image` file).

---

### 3.4 `arm_control.py` — `ArmController`

**Purpose:** Drive the SO-101 through calibration and pixel-coordinate-driven pick-and-place.

| Method | Signature | Description |
|---|---|---|
| `calibrate` | `() -> None` | Opens gripper; moves all joints to home position |
| `pickup_at_coords` | `(x: int, y: int) -> None` | Full pick sequence from pixel coordinates |

#### SO-101 Physical Constants

| Constant | Value | Description |
|---|---|---|
| `L1` | 0.175 m | Upper-arm link length |
| `L2` | 0.135 m | Forearm link length |
| `ARM_REACH_M` | 0.30 m | Max horizontal workspace radius |
| `ARM_HEIGHT_PICKUP_M` | 0.05 m | Z height at object contact |
| `ARM_HEIGHT_LIFT_M` | 0.20 m | Z height for safe transit |
| `IMAGE_WIDTH_PX` | 640 | Camera horizontal resolution |
| `IMAGE_HEIGHT_PX` | 480 | Camera vertical resolution |
| `CAMERA_FOV_X_DEG` | 60° | Camera horizontal field-of-view |
| `CAMERA_FOV_Y_DEG` | 45° | Camera vertical field-of-view |

#### Pickup Sequence

```
pixel (x, y)
  -> _pixel_to_workspace()  -> (wx, wy) metres
  -> _ik(wx, wy, LIFT_Z)    -> angles_above
  -> _ik(wx, wy, PICKUP_Z)  -> angles_pickup
  -> open gripper
  -> move to angles_above  (speed 50)
  -> move to angles_pickup (speed 30)
  -> close gripper
  -> sleep 0.3 s
  -> move to angles_above  (speed 30)  [lift]
```

---

### 3.5 `pick_and_place.py` — Fragility Pipeline

**Purpose:** Classify object fragility via LLM, adapt torque, execute waypoint motion, log result.

```
ObjectInfo(name, description)
  |
  +- [1] Featherless LLM  (Llama-3.1-8B, temperature=0.0, max_tokens=5)
  |        -> "Fragile" | "Robust"
  |
  +- [2] If Fragile -> ElevenLabs TTS
  |        "Handling with care."  (Aria voice, eleven_turbo_v2_5)
  |
  +- [3] Set SO-101 Dynamixel torque limit
  |        Fragile -> 20%   Robust -> 60%
  |
  +- [4] Waypoint motion: home -> pre_pick -> pick -> lift -> pre_place -> place -> home
  |
  +- [5] Toolhouse: google_sheets_append
           Columns: object name, fragility, timestamp
```

#### Waypoints (joint degrees, J1–J6)

| Waypoint | J1 | J2 | J3 | J4 | J5 | J6 |
|---|---|---|---|---|---|---|
| home | 0 | -30 | 90 | -60 | 0 | 0 |
| pre_pick | 45 | 20 | 60 | -45 | 10 | 0 |
| pick | 45 | 35 | 70 | -50 | 10 | 0 |
| lift | 45 | 10 | 55 | -40 | 10 | 0 |
| pre_place | -45 | 20 | 60 | -45 | -10 | 0 |
| place | -45 | 35 | 70 | -50 | -10 | 0 |

---

### 3.6 `main.py` (root) — Standalone Voice Orchestrator

Alternative entry point for direct voice-command operation without the web backend.

```
[1] listen()           -> command string
[2] wake-word check    "pick up" must appear
[3] inventory check    Toolhouse + Scrapegraph AI  (if INVENTORY_URL set)
[4] capture_image()    OpenCV -> snapshot.jpg
[5] detect_object()    RobotVision -> (x, y) pixels
[6] pickup_at_coords   ArmController -> arm motion
[7] log_to_sheet       Toolhouse google_sheets_append  (if SPREADSHEET_ID set)
```

---

## 4. Backend API Reference

Base URL: `http://localhost:8000`

### Health

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Returns `{"status": "ok", "timestamp": "..."}` |

### Elders

| Method | Path | Description |
|---|---|---|
| GET | `/elders` | List all elders |
| POST | `/elders` | Create elder (`full_name`, `timezone`, `primary_language`) |
| GET | `/elders/{id}` | Get single elder |
| GET | `/elders/{id}/medications` | List medications for elder |
| POST | `/elders/{id}/medications` | Add medication (`drug_name`, `strength`, `dosage_form`, `route`) |
| GET | `/elders/{id}/adherence` | List adherence logs for elder |

### Adherence

| Method | Path | Description |
|---|---|---|
| POST | `/adherence/logs` | Log a dose event (`elder_id`, `medication_schedule_id`, `status`) |

Status values: `scheduled` `reminded` `taken` `missed` `skipped` `held_unsafe`

### Alerts

| Method | Path | Description |
|---|---|---|
| GET | `/alerts` | Last 50 notification events |
| WS | `/ws/events` | WebSocket stream of `NotificationEvent` JSON objects |

### Onboarding

| Method | Path | Description |
|---|---|---|
| POST | `/onboarding` | Create patient record (multipart: personal info + doctor's orders PDF) |
| GET | `/onboarding` | List all onboarding records |

### Robot Tasks

| Method | Path | Description |
|---|---|---|
| POST | `/robot/tasks` | Create and immediately execute a robot task |
| GET | `/robot/tasks` | List tasks (optional `?elder_id=` filter) |
| GET | `/robot/tasks/{id}` | Get single task |
| PATCH | `/robot/tasks/{id}` | Manually override task status |

#### `POST /robot/tasks` — pick_and_place payload

```json
{
  "elder_id": "elder_abc123",
  "task_type": "pick_and_place",
  "plan_json": {
    "object_name": "red pill bottle",
    "description": "small red cylindrical bottle on the left side of the tray"
  }
}
```

The backend transitions status `queued → running → completed | failed` and broadcasts each transition over `/ws/events`.

### Voice & Vision

| Method | Path | Description |
|---|---|---|
| POST | `/voice/instruction` | Upload audio file (`file`); returns `{"instruction": "..."}` transcript |
| POST | `/robot/vision/detect` | Upload image (`image`) + `target` string; returns `{"pixel_x": int, "pixel_y": int}` |

---

## 5. Data Flow

### Web → Robot Task Execution

```
Browser (POST /robot/tasks)
  -> FastAPI creates RobotTask (status: queued)
  -> broadcasts "queued" event over /ws/events
  -> asyncio.create_task(_run_robot_task)
        -> status: running  (broadcast)
        -> loop.run_in_executor(pick_and_place(ObjectInfo))
              -> Featherless LLM: fragility classification
              -> ElevenLabs TTS (if Fragile)
              -> lerobot: connect SO-101
              -> waypoint motion sequence
              -> Toolhouse: log to Google Sheets
        -> status: completed | failed  (broadcast)
  -> Browser receives status updates via WebSocket
```

### Voice Command Flow (standalone `main.py`)

```
Microphone -> Smallest.ai STT -> wake-word filter
  -> Toolhouse inventory check (optional)
  -> OpenCV camera snapshot
  -> Featherless VLM object detection -> (x, y)
  -> ArmController IK + motion
  -> Toolhouse spreadsheet log
  -> Smallest.ai TTS -> speaker
```

---

## 6. API & SDK Integrations

### 6.1 Smallest.ai

- **Auth:** `SMALLEST_API_KEY`
- **STT:** `client.speech_to_text.transcribe(file=io.BytesIO(wav_bytes))`
- **TTS:** `client.tts.synthesize(text, model=TTSModels.LIGHTNING, voice_id="emily", sample_rate=24000)`

### 6.2 Featherless.ai

- **Auth:** `FEATHERLESS_API_KEY`
- **SDK:** OpenAI Python SDK with `base_url="https://api.featherless.ai/v1"`
- **VLM (detection):** `Qwen/Qwen2.5-VL-72B-Instruct` — inline base-64 image, `max_tokens=64`
- **LLM (fragility):** `meta-llama/Llama-3.1-8B-Instruct` — text only, `max_tokens=5`, `temperature=0.0`

### 6.3 lerobot (HuggingFace / Cyberwave SO-101)

- **Robot init:** `make_robot(config_dict)` → `robot.connect()`
- **Action dispatch:** `robot.send_action(torch.tensor([...]))` — joint angles ordered by `motor_names`
- **Torque control:** `bus.write("Torque_Limit", values)` (falls back to `Goal_Current` for XM/XH servos)
- **Connection:** USB serial, 1,000,000 baud, `/dev/ttyUSB0`

### 6.4 ElevenLabs

- **Auth:** `ELEVENLABS_API_KEY`
- **Call:** `el_client.text_to_speech.convert(voice_id="9BWtsMINqrJLrRacOk9x", text=..., model_id="eleven_turbo_v2_5")`
- **Voice:** Aria — calm delivery for safety notifications before fragile picks

### 6.5 Toolhouse

- **Auth:** `TOOLHOUSE_API_KEY`
- **Init:** `Toolhouse(api_key=..., provider=Provider.ANTHROPIC)`
- **Pattern:** two-turn Claude tool-use loop — `th.get_tools()` injected into Claude call, `th.run_tools()` executes server-side
- **Active skills:** `google_sheets_append` (pickup log), Scrapegraph AI (inventory check)

### 6.6 Anthropic

- **Auth:** `ANTHROPIC_API_KEY`
- **Model:** `claude-sonnet-4-6`
- **Role:** Backbone LLM for Toolhouse tool-use loops

---

## 7. Inverse Kinematics — Mathematical Model

Closed-form 2-link planar IK extended to 3D via shoulder pan.

### Step 1 — Pixel to Workspace

```
norm_x = (px - W/2) / (W/2)
norm_y = (py - H/2) / (H/2)

wx = norm_x * ARM_REACH_M * tan(FOV_X / 2)
wy = norm_y * ARM_REACH_M * tan(FOV_Y / 2)
```

Assumes a top-down camera over a flat pickup plane.

### Step 2 — Shoulder Pan

```
theta_pan = atan2(wy, wx)
```

### Step 3 — 2-Link Planar IK

```
r    = sqrt(wx² + wy²)
h    = ARM_HEIGHT_LIFT_M - wz
dist = sqrt(r² + h²)  [clamped to L1 + L2 - 1e-4]

cos(theta_elbow) = (L1² + L2² - dist²) / (2·L1·L2)

alpha  = atan2(h, r)
alpha2 = acos((L1² + dist² - L2²) / (2·L1·dist))
theta_shoulder_tilt = alpha + alpha2

theta_wrist_pitch = -(theta_shoulder_tilt - theta_elbow)  [keeps EE level]
```

All joint angles are clamped to `JOINT_LIMITS` before dispatch.

---

## 8. Configuration & Environment Variables

All secrets are loaded from `.env` at the repo root (`D:\hktn\robotichackathon20260313\.env`).

| Variable | Used by | Required | Description |
|---|---|---|---|
| `SMALLEST_API_KEY` | listener.py, backend | Yes | Smallest.ai STT/TTS |
| `FEATHERLESS_API_KEY` | vision.py, pick_and_place.py | Yes | Featherless VLM + LLM |
| `ELEVENLABS_API_KEY` | pick_and_place.py | Yes | ElevenLabs fragility TTS |
| `TOOLHOUSE_API_KEY` | pick_and_place.py, main.py | Yes | Toolhouse skill middleware |
| `ANTHROPIC_API_KEY` | pick_and_place.py, main.py | Yes | Claude (Toolhouse backbone) |
| `PICKUP_SPREADSHEET_ID` | main.py | Optional | Google Sheet ID for pickup log |
| `INVENTORY_URL` | main.py | Optional | Inventory web page for pre-pick check |

### Physical Constants (edit in source)

| File | Constant | Default | Notes |
|---|---|---|---|
| `arm_control.py` | `CAMERA_FOV_X_DEG` | 60° | Must match lens spec |
| `arm_control.py` | `CAMERA_FOV_Y_DEG` | 45° | Must match lens spec |
| `arm_control.py` | `ARM_REACH_M` | 0.30 m | Workspace radius |
| `arm_control.py` | `ARM_HEIGHT_PICKUP_M` | 0.05 m | Contact height |
| `arm_control.py` | `ARM_HEIGHT_LIFT_M` | 0.20 m | Transit clearance |
| `pick_and_place.py` | `TORQUE_FRAGILE` | 20% | Gentle grip |
| `pick_and_place.py` | `TORQUE_ROBUST` | 60% | Firm grip |

---

## 9. Dependencies

### Backend (`backend/`)

```
fastapi
uvicorn
python-multipart
pydantic
python-dotenv
smallest
```

### Robot pipeline (root)

```
openai          # Featherless.ai (OpenAI-compatible)
lerobot         # SO-101 arm control
torch           # required by lerobot
elevenlabs      # fragility TTS
toolhouse       # skill middleware
anthropic       # Toolhouse backbone LLM
opencv-python   # camera capture
pyaudio         # microphone + speaker
```

### Web app (`web-app/`)

```
next@14.2.5
react@18.3.1
react-dom@18.3.1
typescript@5.5.4
```

---

## 10. Known Limitations & Future Work

| ID | Limitation |
|---|---|
| L1 | Simplified 2-link IK — positional error increases at workspace extremes |
| L2 | Top-down camera assumed — wrist-mounted camera needs eye-in-hand calibration |
| L3 | No depth sensor — Z is a fixed constant; cannot handle objects of varying height |
| L4 | Single-frame VLM detection — susceptible to motion blur and occlusion |
| L5 | `audioop` is deprecated in Python 3.13+ |
| L6 | Waypoints in `pick_and_place.py` are hardcoded and must be re-recorded per environment |
| L7 | In-memory data stores — all state is lost on backend restart |

| ID | Proposed Improvement |
|---|---|
| F1 | Full DH-parameter IK or MoveIt! planner |
| F2 | Depth camera (RealSense / ZED) for Z measurement |
| F3 | Continuous VLM tracking on video stream |
| F4 | Persistent database (PostgreSQL / SQLite) for elders, tasks, adherence |
| F5 | Replace `audioop` with `numpy` RMS for Python 3.13 |
| F6 | Re-record waypoints via lerobot teleoperation GUI per deployment |

---

## 11. Setup & Running

### Prerequisites

- Python 3.10 – 3.12
- Node.js 18+
- SO-101 arm powered and connected via USB
- `.env` file at repo root (see Section 8)

### Install

```bash
# Backend
cd backend/
pip install fastapi uvicorn python-multipart pydantic python-dotenv smallest

# Robot pipeline (from repo root)
pip install openai lerobot torch elevenlabs toolhouse anthropic opencv-python pyaudio

# Web app
cd web-app/
npm install
```

### Run

```bash
# Terminal 1 — backend
cd backend/
python -m uvicorn main:app --reload --port 8000

# Terminal 2 — web app
cd web-app/
npm run dev
```

Open http://localhost:3000.

### Create a Robot Pick Task (via UI)

1. Go to `/elders` → create an elder
2. Go to `/robot` → select elder, choose `pick_and_place`
3. Enter **Object name** (required) and **Description** (optional)
4. Click **Create task** — the arm executes immediately; status updates appear live

### Standalone Voice Loop (without web UI)

```bash
# From repo root
python main.py
# Say "pick up the red block" to trigger a full pick cycle
# Say "quit" or Ctrl+C to stop
```

---

*End of Design Document — v2.0*
