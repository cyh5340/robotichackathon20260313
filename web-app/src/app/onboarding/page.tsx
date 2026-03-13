"use client";

import { useEffect, useState } from "react";

import {
  createOnboardingRecord,
  listOnboardingRecords,
  type OnboardingPayload,
} from "@/services/medguard";
import type { OnboardingRecord } from "@/types";

interface InputTarget {
  value: string;
  files?: FileList | null;
}

export default function OnboardingPage() {
  const [fullName, setFullName] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");
  const [doctorName, setDoctorName] = useState("");
  const [doctorContact, setDoctorContact] = useState("");
  const [doctorsOrdersFile, setDoctorsOrdersFile] = useState<File | null>(null);
  const [records, setRecords] = useState<OnboardingRecord[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listOnboardingRecords()
      .then((data: OnboardingRecord[]) => setRecords(data))
      .catch(() => setError("Could not load onboarding records"));
  }, []);

  const onSubmit = async (event: {
    preventDefault: () => void;
  }): Promise<void> => {
    event.preventDefault();
    if (!doctorsOrdersFile) {
      setError("Please upload doctor's orders.");
      return;
    }

    setError(null);
    setSaving(true);

    const payload: OnboardingPayload = {
      fullName,
      dateOfBirth,
      phone,
      email,
      address,
      doctorName,
      doctorContact,
      doctorsOrdersFile,
    };

    try {
      const created = await createOnboardingRecord(payload);
      setRecords((current: OnboardingRecord[]) => [created, ...current]);
      setFullName("");
      setDateOfBirth("");
      setPhone("");
      setEmail("");
      setAddress("");
      setDoctorName("");
      setDoctorContact("");
      setDoctorsOrdersFile(null);
    } catch {
      setError("Could not submit onboarding process");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <section className="card">
        <h1>User Onboarding</h1>
        <p>
          Collect basic user profile information and upload doctor&apos;s
          orders.
        </p>
      </section>

      <section className="card">
        <h2>Onboarding form</h2>
        <form onSubmit={onSubmit}>
          <p>
            <label>
              Full name
              <br />
              <input
                value={fullName}
                onChange={(event: { target: InputTarget }) =>
                  setFullName(event.target.value)
                }
                required
              />
            </label>
          </p>
          <p>
            <label>
              Date of birth
              <br />
              <input
                type="date"
                value={dateOfBirth}
                onChange={(event: { target: InputTarget }) =>
                  setDateOfBirth(event.target.value)
                }
                required
              />
            </label>
          </p>
          <p>
            <label>
              Phone
              <br />
              <input
                value={phone}
                onChange={(event: { target: InputTarget }) =>
                  setPhone(event.target.value)
                }
                required
              />
            </label>
          </p>
          <p>
            <label>
              Email
              <br />
              <input
                type="email"
                value={email}
                onChange={(event: { target: InputTarget }) =>
                  setEmail(event.target.value)
                }
                required
              />
            </label>
          </p>
          <p>
            <label>
              Address
              <br />
              <input
                value={address}
                onChange={(event: { target: InputTarget }) =>
                  setAddress(event.target.value)
                }
                required
              />
            </label>
          </p>
          <p>
            <label>
              Doctor name
              <br />
              <input
                value={doctorName}
                onChange={(event: { target: InputTarget }) =>
                  setDoctorName(event.target.value)
                }
                required
              />
            </label>
          </p>
          <p>
            <label>
              Doctor contact
              <br />
              <input
                value={doctorContact}
                onChange={(event: { target: InputTarget }) =>
                  setDoctorContact(event.target.value)
                }
                required
              />
            </label>
          </p>
          <p>
            <label>
              Doctor&apos;s orders upload
              <br />
              <input
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.txt"
                onChange={(event: { target: InputTarget }) =>
                  setDoctorsOrdersFile(
                    event.target.files && event.target.files.length > 0
                      ? event.target.files[0]
                      : null,
                  )
                }
                required
              />
            </label>
          </p>

          <button type="submit" disabled={saving}>
            {saving ? "Submitting..." : "Submit onboarding"}
          </button>
        </form>
        {error ? <p>{error}</p> : null}
      </section>

      <section className="card">
        <h2>Submitted onboardings</h2>
        {records.length === 0 ? (
          <p>No onboarding records yet.</p>
        ) : (
          <ul>
            {records.map((record: OnboardingRecord) => (
              <li key={record.id}>
                <strong>{record.fullName}</strong> - Doctor: {record.doctorName}
                <br />
                Orders: {record.doctorsOrdersFilename} (
                {record.doctorsOrdersSizeBytes} bytes)
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
