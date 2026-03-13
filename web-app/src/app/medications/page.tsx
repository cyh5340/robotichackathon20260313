"use client";

import { useEffect, useState } from "react";

import {
  createMedication,
  listElders,
  listMedications,
} from "@/services/medguard";
import type { Elder, Medication } from "@/types";

interface InputTarget {
  value: string;
}

export default function MedicationsPage() {
  const [elders, setElders] = useState<Elder[]>([]);
  const [selectedElderId, setSelectedElderId] = useState("");
  const [medications, setMedications] = useState<Medication[]>([]);
  const [drugName, setDrugName] = useState("");
  const [strength, setStrength] = useState("");
  const [dosageForm, setDosageForm] = useState("tablet");
  const [route, setRoute] = useState("oral");
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
      setMedications([]);
      return;
    }
    listMedications(selectedElderId)
      .then((data: Medication[]) => setMedications(data))
      .catch(() => setError("Could not load medications"));
  }, [selectedElderId]);

  const onCreate = async (event: {
    preventDefault: () => void;
  }): Promise<void> => {
    event.preventDefault();
    if (!selectedElderId) return;
    setError(null);
    setSaving(true);
    try {
      const medication = await createMedication(selectedElderId, {
        drugName,
        strength,
        dosageForm,
        route,
      });
      setMedications((current: Medication[]) => [medication, ...current]);
      setDrugName("");
      setStrength("");
    } catch {
      setError("Could not create medication");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <section className="card">
        <h1>Medications</h1>
        <p>Manage medication data for each elder directly from the backend.</p>
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
        {elders.length === 0 ? <p>Create an elder first.</p> : null}
      </section>

      <section className="card">
        <h2>Add medication</h2>
        <form onSubmit={onCreate}>
          <p>
            <label>
              Drug name
              <br />
              <input
                value={drugName}
                onChange={(event: { target: InputTarget }) =>
                  setDrugName(event.target.value)
                }
                required
              />
            </label>
          </p>
          <p>
            <label>
              Strength
              <br />
              <input
                value={strength}
                onChange={(event: { target: InputTarget }) =>
                  setStrength(event.target.value)
                }
                required
              />
            </label>
          </p>
          <p>
            <label>
              Dosage form
              <br />
              <input
                value={dosageForm}
                onChange={(event: { target: InputTarget }) =>
                  setDosageForm(event.target.value)
                }
                required
              />
            </label>
          </p>
          <p>
            <label>
              Route
              <br />
              <input
                value={route}
                onChange={(event: { target: InputTarget }) =>
                  setRoute(event.target.value)
                }
                required
              />
            </label>
          </p>
          <button type="submit" disabled={saving || !selectedElderId}>
            {saving ? "Saving..." : "Create medication"}
          </button>
        </form>
        {error ? <p>{error}</p> : null}
      </section>

      <section className="card">
        <h2>Medication list</h2>
        {medications.length === 0 ? (
          <p>No medications yet for this elder.</p>
        ) : (
          <ul>
            {medications.map((medication: Medication) => (
              <li key={medication.id}>
                <strong>{medication.drugName}</strong> {medication.strength} -{" "}
                {medication.dosageForm} via {medication.route}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
