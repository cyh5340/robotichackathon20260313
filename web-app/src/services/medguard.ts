import { API_BASE_URL, apiRequest } from "@/services/api";
import type { NotificationEvent } from "@/services/notifications";
import type { AdherenceLog, Elder, Medication, OnboardingRecord } from "@/types";

export type AdherenceStatus =
  | "scheduled"
  | "reminded"
  | "taken"
  | "missed"
  | "skipped"
  | "held_unsafe";

export type RobotTaskType = "pick_and_place" | "sort_session";
export type RobotTaskStatus = "queued" | "running" | "completed" | "failed";

interface ElderApi {
  id: string;
  full_name: string;
  timezone: string;
  primary_language: string;
}

interface MedicationApi {
  id: string;
  elder_id: string;
  drug_name: string;
  strength: string;
  dosage_form: string;
  route: string;
}

interface AdherenceLogApi {
  id: string;
  elder_id: string;
  medication_schedule_id: string;
  scheduled_at: string;
  actual_taken_at?: string;
  status: AdherenceStatus;
}

interface NotificationEventApi {
  id: string;
  type: NotificationEvent["type"];
  title: string;
  message: string;
  created_at: string;
}

export interface RobotTask {
  id: string;
  elderId: string;
  taskType: RobotTaskType;
  planJson: Record<string, unknown>;
  status: RobotTaskStatus;
  startedAt: string;
}

interface RobotTaskApi {
  id: string;
  elder_id: string;
  task_type: RobotTaskType;
  plan_json: Record<string, unknown>;
  status: RobotTaskStatus;
  started_at: string;
}

interface OnboardingRecordApi {
  id: string;
  full_name: string;
  date_of_birth: string;
  phone: string;
  email: string;
  address: string;
  doctor_name: string;
  doctor_contact: string;
  doctors_orders_filename: string;
  doctors_orders_content_type: string;
  doctors_orders_size_bytes: number;
  created_at: string;
}

export interface OnboardingPayload {
  fullName: string;
  dateOfBirth: string;
  phone: string;
  email: string;
  address: string;
  doctorName: string;
  doctorContact: string;
  doctorsOrdersFile: File;
}

const toElder = (data: ElderApi): Elder => ({
  id: data.id,
  fullName: data.full_name,
  timezone: data.timezone,
  primaryLanguage: data.primary_language,
});

const toMedication = (data: MedicationApi): Medication => ({
  id: data.id,
  elderId: data.elder_id,
  drugName: data.drug_name,
  strength: data.strength,
  dosageForm: data.dosage_form,
  route: data.route,
});

const toAdherenceLog = (data: AdherenceLogApi): AdherenceLog => ({
  id: data.id,
  elderId: data.elder_id,
  medicationScheduleId: data.medication_schedule_id,
  scheduledAt: data.scheduled_at,
  actualTakenAt: data.actual_taken_at,
  status: data.status,
});

const toNotificationEvent = (data: NotificationEventApi): NotificationEvent => ({
  id: data.id,
  type: data.type,
  title: data.title,
  message: data.message,
  createdAt: data.created_at,
});

const toRobotTask = (data: RobotTaskApi): RobotTask => ({
  id: data.id,
  elderId: data.elder_id,
  taskType: data.task_type,
  planJson: data.plan_json,
  status: data.status,
  startedAt: data.started_at,
});

const toOnboardingRecord = (data: OnboardingRecordApi): OnboardingRecord => ({
  id: data.id,
  fullName: data.full_name,
  dateOfBirth: data.date_of_birth,
  phone: data.phone,
  email: data.email,
  address: data.address,
  doctorName: data.doctor_name,
  doctorContact: data.doctor_contact,
  doctorsOrdersFilename: data.doctors_orders_filename,
  doctorsOrdersContentType: data.doctors_orders_content_type,
  doctorsOrdersSizeBytes: data.doctors_orders_size_bytes,
  createdAt: data.created_at,
});

export function listElders(): Promise<Elder[]> {
  return apiRequest<ElderApi[]>("/elders").then((items: ElderApi[]) => items.map(toElder));
}

export function createElder(payload: {
  fullName: string;
  timezone: string;
  primaryLanguage: string;
}): Promise<Elder> {
  return apiRequest<ElderApi>("/elders", {
    method: "POST",
    body: {
      full_name: payload.fullName,
      timezone: payload.timezone,
      primary_language: payload.primaryLanguage,
    },
  }).then(toElder);
}

export function listMedications(elderId: string): Promise<Medication[]> {
  return apiRequest<MedicationApi[]>(`/elders/${elderId}/medications`).then((items: MedicationApi[]) =>
    items.map(toMedication),
  );
}

export function createMedication(
  elderId: string,
  payload: { drugName: string; strength: string; dosageForm: string; route: string },
): Promise<Medication> {
  return apiRequest<MedicationApi>(`/elders/${elderId}/medications`, {
    method: "POST",
    body: {
      drug_name: payload.drugName,
      strength: payload.strength,
      dosage_form: payload.dosageForm,
      route: payload.route,
    },
  }).then(toMedication);
}

export function listAdherence(elderId: string): Promise<AdherenceLog[]> {
  return apiRequest<AdherenceLogApi[]>(`/elders/${elderId}/adherence`).then((items: AdherenceLogApi[]) =>
    items.map(toAdherenceLog),
  );
}

export function createAdherenceLog(payload: {
  elderId: string;
  medicationScheduleId: string;
  status: AdherenceStatus;
  actualTakenAt?: string;
}): Promise<AdherenceLog> {
  return apiRequest<AdherenceLogApi>("/adherence/logs", {
    method: "POST",
    body: {
      elder_id: payload.elderId,
      medication_schedule_id: payload.medicationScheduleId,
      status: payload.status,
      actual_taken_at: payload.actualTakenAt || null,
    },
  }).then(toAdherenceLog);
}

export function listAlerts(): Promise<NotificationEvent[]> {
  return apiRequest<NotificationEventApi[]>("/alerts").then((items: NotificationEventApi[]) =>
    items.map(toNotificationEvent),
  );
}

export function listRobotTasks(elderId?: string): Promise<RobotTask[]> {
  const path = elderId ? `/robot/tasks?elder_id=${encodeURIComponent(elderId)}` : "/robot/tasks";
  return apiRequest<RobotTaskApi[]>(path).then((items: RobotTaskApi[]) => items.map(toRobotTask));
}

export function createRobotTask(payload: {
  elderId: string;
  taskType: RobotTaskType;
  planJson: Record<string, unknown>;
}): Promise<RobotTask> {
  return apiRequest<RobotTaskApi>("/robot/tasks", {
    method: "POST",
    body: {
      elder_id: payload.elderId,
      task_type: payload.taskType,
      plan_json: payload.planJson,
    },
  }).then(toRobotTask);
}

export function updateRobotTaskStatus(taskId: string, status: RobotTaskStatus): Promise<RobotTask> {
  return apiRequest<RobotTaskApi>(`/robot/tasks/${taskId}`, {
    method: "PATCH",
    body: { status },
  }).then(toRobotTask);
}

export async function transcribeVoiceInstruction(audioBlob: Blob): Promise<string> {
  const formData = new FormData();
  formData.append("file", audioBlob, "instruction.webm");

  const response = await fetch(`${API_BASE_URL}/voice/instruction`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Voice transcription failed: ${response.status}`);
  }

  const payload = (await response.json()) as { instruction: string };
  return payload.instruction;
}

export async function createOnboardingRecord(payload: OnboardingPayload): Promise<OnboardingRecord> {
  const formData = new FormData();
  formData.append("full_name", payload.fullName);
  formData.append("date_of_birth", payload.dateOfBirth);
  formData.append("phone", payload.phone);
  formData.append("email", payload.email);
  formData.append("address", payload.address);
  formData.append("doctor_name", payload.doctorName);
  formData.append("doctor_contact", payload.doctorContact);
  formData.append("doctors_orders", payload.doctorsOrdersFile, payload.doctorsOrdersFile.name);

  const response = await fetch(`${API_BASE_URL}/onboarding`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Onboarding failed: ${response.status}`);
  }

  const record = (await response.json()) as OnboardingRecordApi;
  return toOnboardingRecord(record);
}

export function listOnboardingRecords(): Promise<OnboardingRecord[]> {
  return apiRequest<OnboardingRecordApi[]>("/onboarding").then((items: OnboardingRecordApi[]) =>
    items.map(toOnboardingRecord),
  );
}
