# API Testing Tool

Collection-based API testing: request builder, environments and variables, no-code assertions,
request chaining, data-driven runs, and JUnit/HTML reports.

| Folder | What | Stack |
|---|---|---|
| [backend/](backend) | REST API, request executor, assertion engine, runner, importers, demo target | Python 3.11+, FastAPI, httpx, SQLite |
| [frontend/](frontend) | Web UI | React 19, TypeScript, Tailwind CSS v4, Vite |

## Run locally

```powershell
# backend (API on http://127.0.0.1:8002)
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\apitest.exe

# frontend (UI on http://localhost:5176, proxies /api to 8002)
cd frontend
npm ci
npm run dev
```

On first start the backend seeds a **Demo Store API (sample)** collection and a **Local demo**
environment that target the built-in `/demo` API. Select the environment and run the collection
to see chaining, schema checks and reports end to end.

## Features

- **Requests**: method, URL, query params, headers, JSON/text/XML/form bodies, bearer/basic/API-key auth, timeout, redirects, TLS verification.
- **Variables**: `{{name}}` everywhere; precedence collection < environment < data row < extracted. Dynamic: `{{$uuid}}`, `{{$timestamp}}`, `{{$isoTimestamp}}`, `{{$randomInt}}`, `{{$randomEmail}}`.
- **Assertions**: status (incl. `2xx`), response time, header, JSONPath (`$.items[0].id`, `.length`), body, JSON Schema, type checks; operators equals/contains/</>/regex/exists.
- **Extraction**: JSONPath, header, regex or status into variables for later requests.
- **Runner**: ordered request selection, iterations, CSV/JSON data-driven rows, stop on failure, delay; history with JSON, JUnit XML and HTML reports.
- **Import/export**: cURL (bash/cmd/PowerShell), OpenAPI 3 / Swagger 2 (generates status and JSON Schema contract assertions), Postman v2.x, and native export (secret values blanked).

## Configuration (`APIT_*`)

| Variable | Default | Purpose |
|---|---|---|
| `APIT_PORT` | `8002` | API port (also used for the seeded demo `baseUrl`) |
| `APIT_DB_URL` | `sqlite:///data/apitest.db` | Database location |
| `APIT_TOKEN` | unset | Require `Authorization: Bearer <token>` on `/api/*`; mandatory for non-loopback binds |
| `APIT_ALLOWED_HOSTS` | `*` | Comma-separated targets requests may call (`api.test`, `*.corp.com`). Link-local/cloud-metadata addresses are blocked unless listed explicitly |
| `APIT_MAX_RESPONSE_BYTES` | `5242880` | Response bodies beyond this are truncated |
| `APIT_SEED_DEMO` | `true` | Seed the sample collection on first start |

## Tests

```powershell
cd backend;  .\.venv\Scripts\python.exe -m pytest
cd frontend; npm run typecheck; npm test
```

API docs: http://127.0.0.1:8002/api/docs
