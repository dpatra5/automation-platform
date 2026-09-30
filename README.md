# Automation Platform

One dashboard for load testing, API testing, UI automation and Jira sprint analysis (SprintGuard).

| Service | Folder | Port |
|---|---|---|
| Dashboard (shell UI) | `frontend/` | **3000** |
| Load-testing UI | `frontend/src/components/load-testing/` | 5175 |
| API-testing UI | `frontend/src/components/api-testing/` | 5176 |
| Rewind UI (extension-based UI automation) | `frontend/src/components/ui-automation/` | 5174 |
| SprintGuard API | `backend/sprintguard/` | 8000 |
| Load-testing API | `backend/load-testing/` | 8001 |
| API-testing API | `backend/api-testing/` | 8002 |
| Rewind API | `backend/ui-automation/` | 8003 |
| UI Automation controller (Playwright record / run) | `backend/ui-automation-server/` | 8004 |

## Prerequisites

- Node.js 20+ (tested with 22) and npm 10
- Python 3.11 on `PATH` as `python`
- Git

## Install

From the repository root:

```bash
npm run install:all
```

This installs the root launcher, every frontend, the Playwright controller, the Python requirements and the Playwright Chromium browser.

> **SprintGuard** needs `torch` and `transformers` (several GB). Skip it if you do not need Jira analysis; the other tools run without it.

> **Corporate network:** if npm fails with `UNABLE_TO_GET_ISSUER_CERT_LOCALLY`, configure your company CA (`npm config set cafile <path-to-ca.pem>`) rather than disabling SSL.

### Environment

SprintGuard reads a `.env` file (never committed). Create `backend/sprintguard/.env` if you use it, for example:

```dotenv
JIRA_SERVER=https://your-jira-server
JIRA_TOKEN=<your-jira-personal-access-token>
JIRA_PROJECT_KEY=ABC
JIRA_USE_MOCK=false
HF_TOKEN=<your-hugging-face-token>
# optional: HF_ENDPOINT=<hugging-face-mirror-url>, LLAMA_MODEL_ID=meta-llama/Llama-3.2-1B-Instruct
```

## Run

Start everything (all backends and frontends):

```bash
npm run dev
```

Then open **http://localhost:3000**.

Run only part of it:

```bash
npm run backend      # all APIs
npm run frontend     # all UIs
npm run backend:ui-automation-server   # just the Playwright controller (port 8004)
npm run frontend:shell                 # just the dashboard (port 3000)
```

### Running services one by one (Windows PowerShell)

If `npm run dev` is unavailable (e.g. `concurrently`/`cross-env` could not be installed), start each service in its own terminal from the repository root:

```powershell
# APIs
$env:PYTHONPATH='backend/load-testing/src'; python -m uvicorn lt.api.app:create_app --factory --host 127.0.0.1 --port 8001
$env:PYTHONPATH='backend/api-testing'; python -m uvicorn apitest.main:create_app --factory --host 127.0.0.1 --port 8002
$env:PYTHONPATH='backend/ui-automation'; $env:BASE_URL='http://localhost:8003'; $env:DASHBOARD_URL='http://localhost:5174'; python -m uvicorn app.main:app --host 127.0.0.1 --port 8003
npm --prefix backend/ui-automation-server start
python -m uvicorn backend.sprintguard.main:app --host 127.0.0.1 --port 8000   # optional, needs torch

# UIs
npm --prefix frontend run dev
npm --prefix frontend/src/components/load-testing run dev
npm --prefix frontend/src/components/api-testing run dev
npm --prefix frontend/src/components/ui-automation run dev
```

Health checks: `http://127.0.0.1:8001/healthz`, `:8002/api/v1/health`, `:8003/health`, `:8004/health`.

## UI Automation (Playwright controller)

Open the dashboard → **UI Automation**.

### Record a test

1. Enter the application URL and a **test name**, then click **Start recording**.
2. A Chromium window opens. Use the application normally: click, type, choose options, open links in new tabs, switch tabs, use the browser's Back/Forward/Reload, answer dialogs. Log in once if needed; the session is saved with the test.
3. The toolbar in the bottom-right corner of the page has:
   - **Verify**: click it, then click any element to add a check (the element must be visible and contain the same text on every run).
   - **Dialogs: Accept / Dismiss**: how alert/confirm/prompt dialogs are answered.
   - **Pause / Resume / Stop**.
4. Click **Stop**. The recording is turned into a functional flow and saved to the **Test library**.

What is recorded is *what you did*, not how the mouse moved: clicks, typing (one step per field), selections, check boxes, key presses such as Enter/Escape, navigation, tabs (open / switch / close), Back/Forward/Reload, dialogs, drag and drop and your Verify checks. Mouse movement and scrolling are not steps. When you click something inside a hover menu, the menu you hovered is remembered and hovered again only if the element is hidden.

### Run a test

Open **Test library** → pick a test → **Run test**. Choose the browser (Chromium, Firefox, WebKit) and optional test data (`key=value` per line; values replace fields with a matching label/id/name, or `{{key}}` placeholders).

The test runs step by step like a tester would:

- elements are found by their relative XPath (with fallbacks), scrolling pages and scrollable containers until they appear;
- hover menus are opened when needed; overlays and sticky headers that cover an element are closed or worked around;
- popups and new tabs, tab switches, iframes, modals and dialogs are handled;
- every step is validated (page loaded, URL reached, field value, selected option, checkbox state, Verify text) and the run **stops at the first failure**, marking the remaining steps as skipped;
- if a stored XPath no longer matches cleanly, it is refreshed from the live element and saved.

### Where tests are stored

```
backend/ui-automation-server/data/        (git-ignored: contains saved login cookies)
  <recording-id>.json                     raw recording (events + DOM snapshots)
  <recording-id>.storage.json             saved login state
  tests/<test-name>/test.json             element name → XPath per page / modal / iframe, functional flow, run history
  pages/<site>/<page>.json                page-object repository shared by all tests
```

### Tests

```bash
cd backend/ui-automation-server
npm test
```

## Other tools

- **Load testing** – see [backend/load-testing/README.md](backend/load-testing/README.md).
- **API testing** – see [backend/api-testing/README.md](backend/api-testing/README.md).
- **Rewind (extension-based UI automation)** – see [backend/ui-automation/README.md](backend/ui-automation/README.md).

## Troubleshooting

| Problem | Fix |
|---|---|
| `Could not start Playwright` in UI Automation | Start the controller: `npm --prefix backend/ui-automation-server start` and check `http://127.0.0.1:8004/health`. |
| Chromium is slow to open (10–15 s) | Normal on machines with endpoint scanning; wait for the status to change to *Recording*. |
| `Executable doesn't exist` from Playwright | `npm --prefix backend/ui-automation-server exec playwright install chromium` |
| SprintGuard fails with `No module named 'torch'` | `python -m pip install -r backend/requirements.txt`, or skip SprintGuard. |
| Port already in use | Stop the other process or change the port in the root `package.json` script. |
