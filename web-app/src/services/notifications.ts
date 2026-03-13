export type NotificationEventType =
  | "dose_due"
  | "dose_overdue"
  | "dose_missed"
  | "dose_taken"
  | "unsafe_interaction_detected"
  | "robot_sorting_complete"
  | "manual_review_required";

export interface NotificationEvent {
  id: string;
  type: NotificationEventType;
  title: string;
  message: string;
  createdAt: string;
}
