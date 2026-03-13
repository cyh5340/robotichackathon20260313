export interface SessionUser {
  id: string;
  role: "elder" | "family_caregiver" | "nurse" | "admin";
  email?: string;
}

export interface SessionState {
  accessToken: string;
  user: SessionUser;
}

export function getStoredSession(): SessionState | null {
  const raw = localStorage.getItem("medguard_session");
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SessionState;
  } catch {
    return null;
  }
}

export function setStoredSession(session: SessionState): void {
  localStorage.setItem("medguard_session", JSON.stringify(session));
}

export function clearStoredSession(): void {
  localStorage.removeItem("medguard_session");
}
