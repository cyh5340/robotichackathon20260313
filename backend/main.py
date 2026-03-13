import json
import io
import os
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from smallest import Smallest
except Exception:  # pragma: no cover - handled at request time
    Smallest = None  # type: ignore[assignment]

app = FastAPI(
    title="MedGuard API",
    version="0.1.0",
    description="Minimal FastAPI starter for MedGuard backend domains.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ElderCreate(BaseModel):
    full_name: str
    timezone: str = "America/Los_Angeles"
    primary_language: str = "en"


class Elder(BaseModel):
    id: str
    full_name: str
    timezone: str
    primary_language: str


class MedicationCreate(BaseModel):
    drug_name: str
    strength: str
    dosage_form: str
    route: str


class Medication(BaseModel):
    id: str
    elder_id: str
    drug_name: str
    strength: str
    dosage_form: str
    route: str


class AdherenceLogCreate(BaseModel):
    elder_id: str
    medication_schedule_id: str
    status: Literal["scheduled", "reminded", "taken", "missed", "skipped", "held_unsafe"]
    actual_taken_at: str | None = None


class AdherenceLog(BaseModel):
    id: str
    elder_id: str
    medication_schedule_id: str
    status: str
    scheduled_at: str
    actual_taken_at: str | None = None


class RobotTaskCreate(BaseModel):
    elder_id: str
    task_type: Literal["pick_and_place", "sort_session"]
    plan_json: dict


class RobotTask(BaseModel):
    id: str
    elder_id: str
    task_type: str
    plan_json: dict
    status: Literal["queued", "running", "completed", "failed"]
    started_at: str


class RobotTaskUpdate(BaseModel):
    status: Literal["queued", "running", "completed", "failed"]


NotificationType = Literal[
    "dose_due",
    "dose_overdue",
    "dose_missed",
    "dose_taken",
    "unsafe_interaction_detected",
    "robot_sorting_complete",
    "manual_review_required",
]


class NotificationEvent(BaseModel):
    id: str
    type: NotificationType
    title: str
    message: str
    created_at: str


class VoiceInstructionResponse(BaseModel):
    instruction: str


class OnboardingRecord(BaseModel):
    id: str
    full_name: str
    date_of_birth: str
    phone: str
    email: str
    address: str
    doctor_name: str
    doctor_contact: str
    doctors_orders_filename: str
    doctors_orders_content_type: str
    doctors_orders_size_bytes: int
    created_at: str


ELDERS: dict[str, Elder] = {}
MEDICATIONS: dict[str, Medication] = {}
ADHERENCE_LOGS: dict[str, AdherenceLog] = {}
ROBOT_TASKS: dict[str, RobotTask] = {}
ALERT_EVENTS: list[NotificationEvent] = []
ONBOARDING_RECORDS: dict[str, OnboardingRecord] = {}


class EventConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, payload: NotificationEvent) -> None:
        disconnected: list[WebSocket] = []
        data = json.dumps(payload.model_dump())
        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.append(connection)
        for connection in disconnected:
            self.disconnect(connection)


events = EventConnectionManager()
SMALLEST_CLIENT = None


def create_notification(
    event_type: NotificationType,
    title: str,
    message: str,
) -> NotificationEvent:
    event = NotificationEvent(
        id=f"evt_{uuid4().hex[:8]}",
        type=event_type,
        title=title,
        message=message,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    ALERT_EVENTS.insert(0, event)
    return event


def get_smallest_client():
    global SMALLEST_CLIENT

    if Smallest is None:
        raise HTTPException(
            status_code=503,
            detail="Smallest.ai SDK is not installed on the backend service.",
        )

    api_key = os.environ.get("SMALLEST_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="SMALLEST_API_KEY is not configured on the backend service.",
        )

    if SMALLEST_CLIENT is None:
        SMALLEST_CLIENT = Smallest(api_key=api_key)

    return SMALLEST_CLIENT


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "medguard-api", "version": app.version}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/voice/instruction", response_model=VoiceInstructionResponse)
async def voice_instruction(file: UploadFile = File(...)) -> VoiceInstructionResponse:
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Expected an audio upload.")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio upload is empty.")

    client = get_smallest_client()

    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = file.filename or "instruction.webm"

    try:
        response = client.speech_to_text.transcribe(file=audio_file)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Smallest.ai transcription failed: {exc}") from exc

    instruction = str(getattr(response, "text", "")).strip()
    if not instruction:
        raise HTTPException(status_code=422, detail="No instruction detected in audio.")

    return VoiceInstructionResponse(instruction=instruction)


@app.post("/onboarding", response_model=OnboardingRecord)
async def create_onboarding_record(
    full_name: str = Form(...),
    date_of_birth: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    address: str = Form(...),
    doctor_name: str = Form(...),
    doctor_contact: str = Form(...),
    doctors_orders: UploadFile = File(...),
) -> OnboardingRecord:
    if not doctors_orders.filename:
        raise HTTPException(status_code=400, detail="Doctor's orders file is required.")

    orders_content_type = doctors_orders.content_type or "application/octet-stream"
    orders_bytes = await doctors_orders.read()
    if not orders_bytes:
        raise HTTPException(status_code=400, detail="Doctor's orders file is empty.")

    record = OnboardingRecord(
        id=f"onb_{uuid4().hex[:8]}",
        full_name=full_name,
        date_of_birth=date_of_birth,
        phone=phone,
        email=email,
        address=address,
        doctor_name=doctor_name,
        doctor_contact=doctor_contact,
        doctors_orders_filename=doctors_orders.filename,
        doctors_orders_content_type=orders_content_type,
        doctors_orders_size_bytes=len(orders_bytes),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    ONBOARDING_RECORDS[record.id] = record
    return record


@app.get("/onboarding", response_model=list[OnboardingRecord])
def list_onboarding_records() -> list[OnboardingRecord]:
    return list(ONBOARDING_RECORDS.values())


@app.post("/elders", response_model=Elder)
def create_elder(payload: ElderCreate) -> Elder:
    elder = Elder(id=f"elder_{uuid4().hex[:8]}", **payload.model_dump())
    ELDERS[elder.id] = elder
    return elder


@app.get("/elders", response_model=list[Elder])
def list_elders() -> list[Elder]:
    return list(ELDERS.values())


@app.get("/elders/{elder_id}", response_model=Elder)
def get_elder(elder_id: str) -> Elder:
    elder = ELDERS.get(elder_id)
    if not elder:
        raise HTTPException(status_code=404, detail="Elder not found")
    return elder


@app.post("/elders/{elder_id}/medications", response_model=Medication)
def create_medication(elder_id: str, payload: MedicationCreate) -> Medication:
    if elder_id not in ELDERS:
        raise HTTPException(status_code=404, detail="Elder not found")

    medication = Medication(id=f"med_{uuid4().hex[:8]}", elder_id=elder_id, **payload.model_dump())
    MEDICATIONS[medication.id] = medication
    return medication


@app.get("/elders/{elder_id}/medications", response_model=list[Medication])
def list_medications(elder_id: str) -> list[Medication]:
    if elder_id not in ELDERS:
        raise HTTPException(status_code=404, detail="Elder not found")
    return [m for m in MEDICATIONS.values() if m.elder_id == elder_id]


@app.post("/adherence/logs", response_model=AdherenceLog)
async def create_adherence_log(payload: AdherenceLogCreate) -> AdherenceLog:
    if payload.elder_id not in ELDERS:
        raise HTTPException(status_code=404, detail="Elder not found")

    log = AdherenceLog(
        id=f"adh_{uuid4().hex[:8]}",
        elder_id=payload.elder_id,
        medication_schedule_id=payload.medication_schedule_id,
        status=payload.status,
        scheduled_at=datetime.now(timezone.utc).isoformat(),
        actual_taken_at=payload.actual_taken_at,
    )
    ADHERENCE_LOGS[log.id] = log

    if log.status == "taken":
        event = create_notification(
            "dose_taken",
            "Dose taken",
            f"Dose for elder {log.elder_id} was marked as taken.",
        )
        await events.broadcast(event)
    elif log.status in {"missed", "skipped", "held_unsafe"}:
        event_type: NotificationType = (
            "manual_review_required" if log.status == "held_unsafe" else "dose_missed"
        )
        event = create_notification(
            event_type,
            "Dose attention required",
            f"Dose status for elder {log.elder_id}: {log.status}.",
        )
        await events.broadcast(event)

    return log


@app.get("/elders/{elder_id}/adherence", response_model=list[AdherenceLog])
def list_adherence(elder_id: str) -> list[AdherenceLog]:
    if elder_id not in ELDERS:
        raise HTTPException(status_code=404, detail="Elder not found")
    return [a for a in ADHERENCE_LOGS.values() if a.elder_id == elder_id]


@app.get("/alerts", response_model=list[NotificationEvent])
def list_alerts() -> list[NotificationEvent]:
    return ALERT_EVENTS[:50]


@app.post("/robot/tasks", response_model=RobotTask)
async def create_robot_task(payload: RobotTaskCreate) -> RobotTask:
    if payload.elder_id not in ELDERS:
        raise HTTPException(status_code=404, detail="Elder not found")

    task = RobotTask(
        id=f"task_{uuid4().hex[:8]}",
        elder_id=payload.elder_id,
        task_type=payload.task_type,
        plan_json=payload.plan_json,
        status="queued",
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    ROBOT_TASKS[task.id] = task

    event = create_notification(
        "dose_due",
        "Robot task queued",
        f"Task {task.id} queued for elder {task.elder_id}.",
    )
    await events.broadcast(event)

    return task


@app.get("/robot/tasks", response_model=list[RobotTask])
def list_robot_tasks(elder_id: str | None = None) -> list[RobotTask]:
    tasks = list(ROBOT_TASKS.values())
    if elder_id is None:
        return tasks
    return [task for task in tasks if task.elder_id == elder_id]


@app.get("/robot/tasks/{task_id}", response_model=RobotTask)
def get_robot_task(task_id: str) -> RobotTask:
    task = ROBOT_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Robot task not found")
    return task


@app.patch("/robot/tasks/{task_id}", response_model=RobotTask)
async def update_robot_task(task_id: str, payload: RobotTaskUpdate) -> RobotTask:
    task = ROBOT_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Robot task not found")

    updated_task = task.model_copy(update={"status": payload.status})
    ROBOT_TASKS[task_id] = updated_task

    if payload.status == "completed":
        event = create_notification(
            "robot_sorting_complete",
            "Robot task completed",
            f"Task {task_id} completed for elder {updated_task.elder_id}.",
        )
        await events.broadcast(event)
    elif payload.status == "failed":
        event = create_notification(
            "manual_review_required",
            "Robot task failed",
            f"Task {task_id} failed and needs review.",
        )
        await events.broadcast(event)

    return updated_task


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    await events.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        events.disconnect(websocket)
    except Exception:
        events.disconnect(websocket)
