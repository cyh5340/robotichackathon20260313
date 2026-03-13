"use client";

import { FormEvent, useEffect, useState } from "react";

import { createElder, listElders } from "@/services/medguard";
import type { Elder } from "@/types";

export default function EldersPage() {
  const [elders, setElders] = useState<Elder[]>([]);
  const [fullName, setFullName] = useState("");
  const [timezone, setTimezone] = useState("America/Los_Angeles");
  const [primaryLanguage, setPrimaryLanguage] = useState("en");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listElders()
      .then((data: Elder[]) => setElders(data))
      .catch(() => setError("Could not load elders"));
  }, []);

  const onSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const elder = await createElder({ fullName, timezone, primaryLanguage });
      setElders((current: Elder[]) => [elder, ...current]);
      setFullName("");
    } catch {
      setError("Could not create elder");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <section className="card">
        <h1>Elders</h1>
        <p>Create and review elder profiles stored in the backend.</p>
      </section>

      <section className="card">
        <h2>Add elder</h2>
        <form onSubmit={onSubmit}>
          <p>
            <label>
              Full name
              <br />
              <input
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                required
              />
            </label>
          </p>
          <p>
            <label>
              Timezone
              <br />
              <input
                value={timezone}
                onChange={(event) => setTimezone(event.target.value)}
                required
              />
            </label>
          </p>
          <p>
            <label>
              Primary language
              <br />
              <input
                value={primaryLanguage}
                onChange={(event) => setPrimaryLanguage(event.target.value)}
                required
              />
            </label>
          </p>
          <button type="submit" disabled={saving}>
            {saving ? "Saving..." : "Create elder"}
          </button>
        </form>
        {error ? <p>{error}</p> : null}
      </section>

      <section className="card">
        <h2>Elder list</h2>
        {elders.length === 0 ? (
          <p>No elders yet.</p>
        ) : (
          <ul>
            {elders.map((elder: Elder) => (
              <li key={elder.id}>
                <strong>{elder.fullName}</strong> ({elder.primaryLanguage}) -{" "}
                {elder.timezone}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
