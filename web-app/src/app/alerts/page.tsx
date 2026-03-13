"use client";

import { useEffect, useState } from "react";

import { listAlerts } from "@/services/medguard";
import type { NotificationEvent } from "@/services/notifications";

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<NotificationEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = (): void => {
    setLoading(true);
    setError(null);
    listAlerts()
      .then((data: NotificationEvent[]) => setAlerts(data))
      .catch(() => setError("Could not load alerts"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
  }, []);

  return (
    <>
      <section className="card">
        <h1>Alerts</h1>
        <p>
          Review reminder escalations and safety notifications from live backend
          data.
        </p>
        <button onClick={refresh} disabled={loading}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
        {error ? <p>{error}</p> : null}
      </section>

      <section className="card">
        <h2>Recent alerts</h2>
        {alerts.length === 0 ? (
          <p>No alerts yet.</p>
        ) : (
          <ul>
            {alerts.map((alert: NotificationEvent) => (
              <li key={alert.id}>
                <strong>{alert.type}</strong> - {alert.title} ({alert.createdAt}
                )
                <br />
                {alert.message}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
