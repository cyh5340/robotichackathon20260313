export interface Elder {
  id: string;
  fullName: string;
  timezone: string;
  primaryLanguage: string;
}

export interface Medication {
  id: string;
  elderId: string;
  drugName: string;
  strength: string;
  dosageForm: string;
  route: string;
}

export interface AdherenceLog {
  id: string;
  elderId: string;
  medicationScheduleId: string;
  scheduledAt: string;
  actualTakenAt?: string;
  status: "scheduled" | "reminded" | "taken" | "missed" | "skipped" | "held_unsafe";
}

export interface OnboardingRecord {
  id: string;
  fullName: string;
  dateOfBirth: string;
  phone: string;
  email: string;
  address: string;
  doctorName: string;
  doctorContact: string;
  doctorsOrdersFilename: string;
  doctorsOrdersContentType: string;
  doctorsOrdersSizeBytes: number;
  createdAt: string;
}
