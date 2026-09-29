import { useEffect } from "react";

const LOAD_TESTING_APP_URL =
  import.meta.env.VITE_LOAD_TESTING_APP_URL ?? "http://localhost:5175";

export function LoadTestingPage() {
  // The tool sends X-Frame-Options: DENY in production, so it runs in its own tab.
  useEffect(() => {
    window.open(LOAD_TESTING_APP_URL, "_blank", "noopener,noreferrer");
  }, []);

  return (
    <div className="page">
      <h1>Load Testing</h1>
      <p className="page-description">
        The Load Testing tool opened in a new tab. Use it to auto-scan an app's
        APIs, create load runs, and analyze rate-limit behaviour.
      </p>
      <a
        className="run-btn"
        href={LOAD_TESTING_APP_URL}
        target="_blank"
        rel="noreferrer"
      >
        Open Load Testing Tool
      </a>
    </div>
  );
}
