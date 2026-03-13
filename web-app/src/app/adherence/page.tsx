"use client";

import { useEffect, useState } from "react";

import {
  createAdherenceLog,
  listAdherence,
  listElders,
} from "@/services/medguard";
import type { AdherenceLog, Elder } from "@/types";

interface InputTarget {
  value: string;
}

const STATUS_OPTIONS: AdherenceLog["status"][] = [
  "scheduled",
  "reminded",
  "taken",
  "missed",
  "skipped",
  "held_unsafe",
];

export default function AdherencePage() {
  const [elders, setElders] = useState<Elder[]>([]);
  const [selectedElderId, setSelectedElderId] = useState("");
  const [logs, setLogs] = useState<AdherenceLog[]>([]);
  const [medicationScheduleId, setMedicationScheduleId] =
    useState("schedule_demo");
  const [status, setStatus] = useState<AdherenceLog["status"]>("taken");
  const [actualTakenAt, setActualTakenAt] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listElders()
      .then((data: Elder[]) => {
        setElders(data);
        if (data.length > 0) {
          setSelectedElderId(data[0].id);
        }
      })
      .catch(() => setError("Could not load elders"));
  }, []);

  useEffect(() => {
    if (!selectedElderId) {
      setLogs([]);
      return;
    }
    listAdherence(selectedElderId)
      .then((data: AdherenceLog[]) => setLogs(data))
      .catch(() => setError("Could not load adherence logs"));
  }, [selectedElderId]);

  const onCreate = async (event: {
    preventDefault: () => void;
  }): Promise<void> => {
    event.preventDefault();
    if (!selectedElderId) return;

    setError(null);
    setSaving(true);

    try {
      const created = await createAdherenceLog({
        elderId: selectedElderId,
        medicationScheduleId,
        status,
        actualTakenAt: actualTakenAt || undefined,
      });
      setLogs((current: AdherenceLog[]) => [created, ...current]);
      setActualTakenAt("");
    } catch {
      setError("Could not create adherence log");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <section className="card">
        <h1>Adherence</h1>
        <p>Log and review dose statuses with backend data.</p>
      </section>

      <section className="card">
        <h2>Select elder</h2>
        <select
          value={selectedElderId}
          onChange={(event: { target: InputTarget }) =>
            setSelectedElderId(event.target.value)
          }
        >
          {elders.map((elder: Elder) => (
            <option key={elder.id} value={elder.id}>
              {elder.fullName}
            </option>
          ))}
        </select>
      </section>

      <section className="card">
        <h2>Log dose status</h2>
        <form onSubmit={onCreate}>
          <p>
            <label>
              Medication schedule id
              <br />
              <input
                value={medicationScheduleId}
                onChange={(event: { target: InputTarget }) =>
                  setMedicationScheduleId(event.target.value)
                }
                required
              />
            </label>
          </p>
          <p>
            <label>
              Status
              <br />
              <select
                value={status}
                onChange={(event: { target: InputTarget }) =>
                  setStatus(event.target.value as AdherenceLog["status"])
                }
              >
                {STATUS_OPTIONS.map((entry: AdherenceLog["status"]) => (
                  <option key={entry} value={entry}>
                    {entry}
                  </option>
                ))}
              </select>
            </label>
          </p>
          <p>
            <label>
              Actual taken at (optional ISO timestamp)
              <br />
              <input
                value={actualTakenAt}
                onChange={(event: { target: InputTarget }) =>
                  setActualTakenAt(event.target.value)
                }
              />
            </label>
          </p>
          <button type="submit" disabled={saving || !selectedElderId}>
            {saving ? "Saving..." : "Create log"}
          </button>
        </form>
        {error ? <p>{error}</p> : null}
      </section>

      <section className="card">
        <h2>Recent adherence</h2>
        {logs.length === 0 ? (
          <p>No adherence logs yet.</p>
        ) : (
          <ul>
            {logs.map((log: AdherenceLog) => (
              <li key={log.id}>
                <strong>{log.status}</strong> - schedule{" "}
                {log.medicationScheduleId} at {log.scheduledAt}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
