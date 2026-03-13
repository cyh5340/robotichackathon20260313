import { DashboardClient } from "@/components/common/DashboardClient";

export default function DashboardPage() {
  return (
    <>
      <h1>MedGuard Dashboard</h1>
      <p>
        Live operational view connected to MedGuard backend APIs and realtime
        alerts.
      </p>
      <DashboardClient />
    </>
  );
}
