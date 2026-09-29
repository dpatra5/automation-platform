import { useEffect } from "react";

const API_TESTING_APP_URL =
  import.meta.env.VITE_API_TESTING_APP_URL ?? "http://localhost:5176";

export function ApiTestingPage() {
  useEffect(() => {
    window.open(API_TESTING_APP_URL, "_blank", "noopener,noreferrer");
  }, []);

  return (
    <div className="page">
      <h1>API Testing</h1>
      <p className="page-description">
        The API Testing tool opened in a new tab. Build request collections, add
        assertions and chained variables, import from cURL, OpenAPI or Postman,
        and run data-driven suites with JUnit/HTML reports.
      </p>
      <a
        className="run-btn"
        href={API_TESTING_APP_URL}
        target="_blank"
        rel="noreferrer"
      >
        Open API Testing Tool
      </a>
    </div>
  );
}
