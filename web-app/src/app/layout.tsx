import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "MedGuard Web",
  description: "Caregiver dashboard shell for MedGuard",
};

export default function RootLayout({ children }: { children: any }) {
  return (
    <html lang="en">
      <body>
        <header className="app-header">
          <div className="app-header-inner">
            <div className="brand-block">
              <p className="brand-kicker">MedGuard Care Portal</p>
              <p className="brand-tagline">
                Large-text, calm interface designed for caregivers and older
                adults.
              </p>
            </div>
            <nav className="nav" aria-label="Primary navigation">
              <Link href="/" className="nav-link">
                Dashboard
              </Link>
              <Link href="/onboarding" className="nav-link">
                Onboarding
              </Link>
              <Link href="/elders" className="nav-link">
                Elders
              </Link>
              <Link href="/medications" className="nav-link">
                Medications
              </Link>
              <Link href="/adherence" className="nav-link">
                Adherence
              </Link>
              <Link href="/alerts" className="nav-link">
                Alerts
              </Link>
              <Link href="/robot" className="nav-link">
                Robot
              </Link>
            </nav>
          </div>
        </header>
        <main className="app-main">{children}</main>
      </body>
    </html>
  );
}
