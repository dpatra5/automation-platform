# 🔄 Rewind — Regression Testing Automation Platform

**Record once. Replay endlessly. Evidence everything.**

Rewind is a regression testing automation platform that lets testers record browser flows once, save them as structured test cases, and re-trigger them from a web dashboard. Each run opens Chrome at the test case's start URL and traverses every recorded step, capturing a per-step screenshot, video, a Playwright trace, and the real console and network logs as regression evidence.

Runs are **headed by default** — you watch Chrome drive the flow, and the dashboard
timeline fills in step by step while it happens. Set `HEADLESS=true` for CI or a
headless server.

---

## 🏗️ Architecture Overview

```
rewind/
├── frontend/      # React + TypeScript + Vite dashboard
├── backend/       # Python FastAPI + Playwright execution engine
├── extension/     # Chrome MV3 extension (the recorder)
├── docker-compose.yml
└── README.md
```

### Layering Rules

The backend enforces strict architectural layering:

```
┌─────────────────────────────────┐
│         API Routers             │  ← Validate → Call Service → Return DTO
├─────────────────────────────────┤
│         Services                │  ← ALL business logic lives here
├─────────────────────────────────┤
│       Repositories              │  ← ALL DB access, one class per aggregate
├─────────────────────────────────┤
│      SQLAlchemy Models          │  ← ORM models only
└─────────────────────────────────┘
```

- **Routers** contain NO business logic and NO DB queries — they call services only
- **Services** never import SQLAlchemy models directly — they use repositories
- **Step handlers** use a registry/strategy pattern — adding a new action type means adding one handler class
- **Integrations** implement abstract base classes — the app runs with `noop_client` when no credentials are configured
- **All external I/O** (Playwright, HTTP clients, filesystem) is injected via constructor for testability

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+** with pip
- **Node.js 18+** with npm
- **Google Chrome** (for the extension)
- **Docker** and **Docker Compose** (optional, for containerized deployment)

### Option 1: Docker Compose (Recommended)

```bash
# Clone the repository
cd rewind

# Start everything
docker-compose up --build

# The frontend will be available at http://localhost:5173
# The backend API will be available at http://localhost:8000
```

### Option 2: Manual Setup

#### Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Run the seed script to populate demo data
python -m scripts.seed

# Start the backend server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev

# The dashboard will be available at http://localhost:5173
```

#### Chrome Extension

1. Build it first — `chrome://extensions` loads `extension/dist/`, not the source:
   ```bash
   cd extension && npm install && npm run build
   ```
2. Open Chrome and navigate to `chrome://extensions/`
3. Enable **Developer mode** (toggle in the top-right corner)
4. Click **Load unpacked**
5. Navigate to `rewind/extension/dist/` and select it
6. The Rewind extension icon will appear in your toolbar

> **After every `npm run build`, press the ↻ reload button on the Rewind card in
> `chrome://extensions`.** Chrome keeps running the previously loaded copy
> otherwise. The project page shows an **Extension connected** / **Extension not
> detected** chip so you can tell at a glance which state you are in.

### No floating bar on the target site?

The bar is drawn by the extension's content script, so it appears only when the
extension is loaded, reloaded after the last build, and actually recording.

| Symptom                                      | Cause                                                                  | Fix                                                                                                             |
| -------------------------------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Project page says **Extension not detected** | The extension is not loaded, or this tab was open before it was loaded | Load/reload it in `chrome://extensions`, then reload the dashboard tab                                          |
| Pressing **Record new test** does nothing    | Same as above, on an older build                                       | Rebuild, reload the extension, reload the page — the button now reports the failure instead of failing silently |
| The app tab never opens                      | The browser blocked the popup                                          | Allow popups for the dashboard, or open the app URL yourself — the bar appears there either way                 |
| Bar missing on one specific site             | That page reloaded before the extension attached                       | Reload the page; the bar re-mounts within a second                                                              |

The extension reaches into pages that were already open when it loaded, so an
existing dashboard tab does not have to be reopened after the first install —
but a tab open across an extension _reload_ still needs a refresh.

To build the extension:

```bash
cd extension

# Install dependencies
npm install

# Build
npm run build

# Or watch mode for development
npm run dev
```

---

## 🌱 Seed Data

The seed script creates demo data so the app is immediately demo-able:

```bash
cd backend
python -m scripts.seed
```

> The seed script drops and recreates the schema. An existing `rewind.db` from an
> earlier version does **not** need re-seeding: the backend adds any missing
> tables and columns on startup. Databases created before the `ON DELETE CASCADE`
> foreign keys were added still work for everything except
> `DELETE /api/v1/test-cases/{id}`, which will refuse to delete a test case that
> has runs. Re-seed to get those.

This creates:

- **Rewind Demo** project (base URL: `https://demo.playwright.dev/todomvc`)
- **Add and complete todo** test case — navigates to the site, fills the todo input, presses Enter, clicks the checkbox
- **Filter active todos** test case — navigates, adds a todo, clicks the "Active" filter link

---

## 📡 API Endpoints

| Method   | Endpoint                               | Description                                                       |
| -------- | -------------------------------------- | ----------------------------------------------------------------- |
| `GET`    | `/api/v1/projects`                     | List all projects                                                 |
| `POST`   | `/api/v1/projects`                     | Create a project                                                  |
| `GET`    | `/api/v1/projects/{id}`                | Get project details                                               |
| `PATCH`  | `/api/v1/projects/{id}`                | Update a project, including its Jira key                          |
| `GET`    | `/api/v1/projects/{id}/test-cases`     | List test cases for a project                                     |
| `GET`    | `/health`                              | Liveness, used by the compose healthcheck                         |
| `POST`   | `/api/v1/projects/{id}/auth-profile`   | Upload auth profile (storage state)                               |
| `GET`    | `/api/v1/projects/{id}/auth-profile`   | Session status — expiry, cookie count, origins; never the cookies |
| `DELETE` | `/api/v1/projects/{id}/auth-profile`   | Forget the stored session                                         |
| `GET`    | `/api/v1/test-cases/{id}`              | Get test case with steps                                          |
| `PUT`    | `/api/v1/test-cases/{id}`              | Update test case                                                  |
| `PUT`    | `/api/v1/test-cases/{id}/steps`        | Replace the steps and exit criteria                               |
| `DELETE` | `/api/v1/test-cases/{id}`              | Delete test case                                                  |
| `POST`   | `/api/v1/test-cases/{id}/run`          | Trigger a test run                                                |
| `GET`    | `/api/v1/runs`                         | List runs (filterable)                                            |
| `GET`    | `/api/v1/runs/{id}`                    | Get run with results & evidence                                   |
| `GET`    | `/api/v1/runs/{id}/evidence/{eid}`     | Download evidence file                                            |
| `GET`    | `/api/v1/run-batches`                  | List sequential run batches                                       |
| `POST`   | `/api/v1/run-batches`                  | Replay several test cases in sequence                             |
| `GET`    | `/api/v1/run-batches/{id}`             | Batch with every run and the report path                          |
| `POST`   | `/api/v1/recordings`                   | Submit a recorded session                                         |
| `GET`    | `/api/v1/recordings/session-token`     | Get session token for extension                                   |
| `GET`    | `/api/v1/integrations/assertions`      | The check catalogue the GUIs render                               |
| `GET`    | `/api/v1/integrations/jira/status`     | Whether Jira credentials are configured                           |
| `GET`    | `/api/v1/integrations/jira/validate`   | Verify a Jira Test Execution key                                  |
| `POST`   | `/api/v1/integrations/test-connection` | Test integration connectivity                                     |

---

## 🎯 Data Model

```
Project        → id, name, base_url, description, jira_key, created_at
AuthProfile    → id, project_id, name, storage_state_json, expires_at
TestCase       → id, project_id, name, description, start_url, created_at
Step           → id, test_case_id, order_index, action, selector,
                 selector_strategy, value, assertion_type, expected_value,
                 is_exit_criteria
RunBatch       → id, project_id, name, status, started_at, finished_at,
                 report_path, jira_issue_key, jira_status, jira_error
TestRun        → id, test_case_id, status, started_at, finished_at,
                 trigger_source, error_message, batch_id, batch_order,
                 jira_issue_key, jira_status, jira_error
StepResult     → id, test_run_id, step_id, status, duration_ms,
                 screenshot_path, error_message
Evidence       → id, test_run_id, type, file_path, created_at
```

### Enums

| Enum                | Values                                                                                                                                                                                                                                                                                                     |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `action`            | **Navigation:** `navigate`, `reload`, `go_back`, `go_forward` · **Pointer:** `click`, `dblclick`, `right_click`, `hover`, `drag`, `scroll` · **Input:** `fill`, `type`, `press_key`, `select`, `check`, `uncheck`, `upload` · **Wait:** `wait`, `wait_for_selector`, `wait_for_url` · **Verify:** `assert` |
| `selector_strategy` | `test_id`, `role`, `text`, `css`, `xpath`                                                                                                                                                                                                                                                                  |
| `assertion_type`    | ~45 checks across Text, Input value, Dropdown, State, Attribute, Count and Page — see below                                                                                                                                                                                                                |
| `status`            | `pending`, `running`, `passed`, `failed`, `error`                                                                                                                                                                                                                                                          |
| `evidence_type`     | `screenshot`, `video`, `trace`, `console_log`, `network_log`, `report`                                                                                                                                                                                                                                     |
| `jira_status`       | `skipped`, `posted`, `failed`                                                                                                                                                                                                                                                                              |

Every action is editable in the dashboard, so a recorded flow can be tightened
with explicit waits and assertions after the fact.

---

## ✅ Exit criteria

A replay that clicks through a flow without checking anything only proves the
selectors still resolve. Exit criteria are the checks that decide whether the
flow actually _worked_ — they run after the last recorded step, and the run only
passes when every one of them holds.

They can be added in two places:

- **While recording.** Press **Add check** on the floating bar, click the element
  you care about, and pick a condition. The picker suggests the checks that suit
  that element (a dropdown offers "selected option is", a text box offers "value
  is", a button offers "is enabled") and pre-fills the value it currently holds.
- **In the dashboard.** The test case page has an **Exit criteria** section with
  the same picker, plus the full catalogue.

The catalogue is served by `GET /api/v1/integrations/assertions` and generated
from the one module that evaluates it (`app/execution/assertions.py`), so the
dashboard and the recorder can never offer a check the runner does not know:

| Group           | Examples                                                                                                         |
| --------------- | ---------------------------------------------------------------------------------------------------------------- |
| **Text**        | contains, does not contain, is exactly, matches a regex, length is / at least / at most, is empty                |
| **Input value** | is exactly, contains, matches, length checks, is empty, number equals / at least / at most                       |
| **Dropdown**    | selected option value, selected label, number of selected options, number of options, has an option              |
| **State**       | visible, hidden, exists, is not in the page, enabled, disabled, editable, read-only, checked, unchecked, focused |
| **Attribute**   | attribute is / contains / is present, has CSS class, does not have CSS class, computed style is                  |
| **Count**       | matching elements equals / at least / at most                                                                    |
| **Page**        | URL contains / is / matches, page title contains / is                                                            |

A check that is misconfigured (an unparseable regex, a missing attribute name)
says so plainly instead of reporting the page as broken.

---

## 🔁 Running several test cases in sequence

Tick more than one test case on a project and press **Run N in sequence**. The
runs execute one after another — never in parallel, since they share the
application's state and its signed-in session — and a failing leg does not stop
the rest, because the point of a suite report is to see everything that broke.

When the last one finishes, Rewind writes a consolidated report to
`artifacts/batches/{batch_id}/`:

- `report.html` — overall verdict, per-test-case results, every step with its
  timing and screenshot, and links to all the evidence
- `report.json` — the same data, for anything downstream

The sequence page (`/sequences/{id}`) shows progress while it runs and links to
the report and each individual run.

**Ambiguous selectors.** A selector that was unique while recording can match
several elements on replay — restoring a session brings back rows and list items
that were not there before. Steps act on the first match rather than failing, and
the run's `console.log` records an `AMBIGUOUS` line naming the selector and the
match count, so a genuine duplicate is still visible in the evidence.

**State classes are never recorded.** An app marks elements as it goes —
TodoMVC adds `completed` the instant a row is ticked, tab strips add `active`.
A selector built from the post-click DOM (`li.completed > input.toggle`) can only
match _after_ the very action it performs, so it never replays. The selector
engine drops classes that describe state rather than identity, and checkbox
selectors are captured on `pointerdown`, before the app reacts. A run that fails
on a recording made before this says which class is at fault instead of only
reporting a timeout.

---

## 🧪 Running Tests

```bash
cd backend
pytest -v
```

Tests cover:

- Step handler registry dispatch
- The exit-criteria check catalogue, and that every published check is runnable
- Selector-strategy locator resolution
- Run lifecycle state transitions, including exit-criteria ordering
- Repository CRUD operations

All tests mock Playwright — no real browsers are launched.

For an end-to-end check that _does_ launch a browser (throwaway database and
artifacts directory, nothing in the project is touched):

```bash
cd backend
python -m scripts.smoke_run
```

It asserts that a flow passes with screenshots and console/network/video/trace
evidence, that the wider action set replays, that exit criteria run after the
recorded steps and decide the verdict, that several test cases replay in
sequence and produce one consolidated report, that step results appear _while
the run is still going_, that a broken selector fails the run with a failure
screenshot, and that an expired session stops the run before the browser opens.
It deliberately runs on a `SelectorEventLoop` — the loop `uvicorn --reload` uses
on Windows, where Playwright's driver subprocess cannot be spawned — so it
regression-tests the worker-thread event loop the runner sets up for itself.

To exercise the whole loop including the real Chrome extension — dashboard →
record → save → replay — start all three services and run:

```bash
cd backend && python -m scripts.smoke_extension
```

It loads `extension/dist` into Chromium, starts a recording from the dashboard,
drives a flow, stops it from the floating island, and replays what the extension
saved. Set `REWIND_DASHBOARD` if Vite fell back off port 5173.

---

## 🔌 Extension: How Recording Works

1. The web app requests a session token from the backend and opens the project's base URL in a new tab
2. The web app `postMessage`s the token + project ID to its own window; the extension's content script (which runs on every page) relays it to the service worker. A page cannot message a service worker directly, and the relay only accepts messages from the dashboard's own origin
3. A **floating island** appears at the bottom of the recorded page showing a live timer, the step count, the last captured action, and **Pause** / **Stop** buttons. It lives in a shadow root so the host page cannot restyle it, and it ignores its own clicks. The extension popup mirrors the same state and controls
4. The service worker locks onto the first non-dashboard tab that loads. Clicks in the dashboard itself are never recorded

### What gets captured

| Event                            | Recorded as                                                                                                                                                                 |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Click, double-click, right-click | `click`, `dblclick`, `right_click` (the two clicks before a double-click are dropped)                                                                                       |
| Typing                           | `fill` — buffered from `input` events and flushed on the next action, so text is kept even when a field is submitted with Enter and never blurs                             |
| Dropdown, checkbox, radio        | `select`, `check`, `uncheck` — a multi-select records every chosen option, separated by `\|\|`                                                                              |
| File picker                      | `upload` (filenames only — point the step at a path the runner can read)                                                                                                    |
| Keys                             | `press_key` for `Enter`, `Tab`, `Escape`, `Backspace`, `Delete`, arrows, Home/End/PageUp/PageDown, and any modifier combo such as `Control+A`                               |
| Drag and drop                    | `drag`, with the drop target in `value`                                                                                                                                     |
| Hovering                         | `hover`, but only when it matters — the pointer resting on an element _and_ the page reacting to it. Menus and tooltips are replayable; idle mouse movement is not recorded |
| Scrolling                        | `scroll` at the resting position, for the window **and** for any scrollable container, so a regression below the fold or inside a virtualised list is still reachable       |
| Navigation                       | `navigate`, plus `wait_for_url` when returning from a sign-in detour                                                                                                        |
| Back, Forward, Reload            | `go_back`, `go_forward`, `reload` — Chrome reports both directions the same way, so the recorded history is what decides which it was                                       |
| Exit criteria                    | `assert`, added from the **Add check** button on the floating bar                                                                                                           |

5. The **selector engine** generates stable selectors using a priority cascade:
   - `data-testid` / `data-test` / `data-cy` attributes (most stable)
   - ARIA role + accessible name
   - Unique visible text content
   - Stable CSS path (skipping auto-generated class names)
   - Absolute XPath (last resort)
6. Steps are buffered in `chrome.storage.session` to survive page navigation
7. On stop, the extension POSTs the steps **and the browser session** to the backend, then opens the test case in the dashboard

---

## 🔐 Authentication and SSO

A regression test is only useful if it can reach the app. Rewind handles sign-in
without ever recording a credential:

- **Nothing on the identity provider is recorded.** The moment the recorded tab
  leaves the project's own origin, capture suspends and the island turns blue
  with _"Sign-in page — not recorded"_. No password, no MFA code, no IdP-specific
  clicks end up in the test case.
- **The session is captured instead.** When recording stops, the extension reads
  the cookies of every host visited plus the page's `localStorage` and sends them
  as a Playwright `storage_state`. Replayed runs start already signed in.
- **Coming back from the IdP becomes a step.** The redirect chain is recorded as
  `wait_for_url`, so replay waits for the app to actually land rather than racing
  the next click.
- **Expiry is checked up front, with a buffer.** The stored expiry is the earliest
  expiring cookie; a run is refused if that is less than **5 minutes** away
  (`EXPIRY_BUFFER` in `app/execution/auth_manager.py`), so a long run cannot lose
  its session halfway. The failure says exactly what to do instead of surfacing a
  timeout on a login form. Session-only cookies have no clock, so those runs are
  attempted and diagnosed at runtime instead.
- **A run that lands on a login page says so.** If the saved session is rejected,
  the error names the sign-in URL rather than reporting "element not found".
- **The dashboard never sees the cookies.** `GET /projects/{id}/auth-profile`
  returns the expiry, the cookie count and the origins — never the session values.
- The session file the runner writes is deleted after every run.

For apps that are scripted rather than recorded, paste a Playwright
`storage_state` straight into the Authentication panel on the project page.

---

## 🔗 Integrations

### Jira

A project can name one Jira **Test Execution** issue, e.g. `JGQE-23122`. When a
run or a sequence finishes, Rewind comments on it with the verdict, a step-by-step
table, the failures, and the evidence attached to the issue.

- **The key is verified before it is stored.** Rewind looks the issue up, checks
  it exists, and checks its type is `Test Execution` (configurable). A typo that
  would silently swallow every report is rejected with a sentence saying why.
- **Reporting never fails a run.** If Jira is down, unreachable or refuses the
  token, the run keeps its own result and the dashboard shows what went wrong on
  the run itself.
- **A sequence comments once**, not once per test case, and attaches the
  consolidated report alongside the evidence.

Credentials live in `backend/.env` and never in the database:

```env
# Jira Data Center / Server — Personal Access Token
JIRA_URL=https://jira.yourcompany.com
JIRA_TOKEN=your-personal-access-token

# Jira Cloud — account email + API token (basic auth)
# JIRA_EMAIL=you@yourcompany.com
```

Restart the backend after editing `.env`. Without `JIRA_URL` and `JIRA_TOKEN`
the integration simply stays off, and the project page says so.

### Others

| Integration    | Status     | Description                                             |
| -------------- | ---------- | ------------------------------------------------------- |
| **Jira**       | ✅ Live    | Verifies the Test Execution key, comments with evidence |
| **Confluence** | Stub       | Publish test reports as pages                           |
| **Bitbucket**  | Stub       | Comment on PRs with test results                        |
| **No-op**      | ✅ Default | Runs without any external credentials                   |

The app always runs with `noop_client` when no credentials are configured — it never crashes on missing integration config.

To implement a real integration, create a class that extends the abstract `IssueTracker` or `DocStore` interface.

---

## 🐳 Docker

```bash
# Build and start
docker-compose up --build

# Stop
docker-compose down

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend
```

---

## 📁 Evidence Storage

All test run evidence is stored under `backend/artifacts/{run_id}/`:

```
artifacts/
├── {run_id}/
│   ├── step_{order}_screenshot.png   # one per executed step
│   ├── failure.png                   # only when the run failed
│   ├── page@{hash}.webm              # video
│   ├── trace.zip                     # Playwright trace
│   ├── console.log                   # step trace + browser console + page errors
│   └── network.log                   # every request, response and failure
└── batches/{batch_id}/
    ├── report.html                   # consolidated report for a sequence
    └── report.json                   # the same data, machine-readable
```

### Opening a trace

`trace.zip` is not a report you can unzip and read — it only makes sense in the
Playwright trace viewer, which replays the run with a DOM snapshot at every
action:

```bash
npx playwright show-trace path/to/trace.zip
```

or drop the file on [trace.playwright.dev](https://trace.playwright.dev), which
runs locally in the browser and uploads nothing. The **Trace** button on a run
carries the same instructions.

### Why a run may have no video file

Headed Chrome only paints its recording surface while the window is in front, so
a run left behind another window can film white or black frames. Rewind raises
the browser window before the first step, discards a film file that never
received a frame, and the **Replay** tab falls back to playing the run back from
the per-step screenshots — which the runner always captures. Every run therefore
has something to watch.

For a video _file_ every time, run headless (`HEADLESS=true`). Set `VIDEO=off` to
skip filming altogether.

Evidence files are served via the `/artifacts/` static file route.

---

## ⚙️ Configuration

All configuration is environment-driven via `backend/app/config.py`:

| Variable                             | Default                                       | Description                                                                                                                                                                                                                                                                                                                                                              |
| ------------------------------------ | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `DATABASE_URL`                       | `sqlite+aiosqlite:///./data/rewind.db`        | Database connection string                                                                                                                                                                                                                                                                                                                                               |
| `ARTIFACTS_DIR`                      | `./artifacts`                                 | Directory for test evidence                                                                                                                                                                                                                                                                                                                                              |
| `DASHBOARD_URL`                      | `http://localhost:5173`                       | Used for the deep links written into Jira comments                                                                                                                                                                                                                                                                                                                       |
| `CORS_ORIGINS`                       | `http://localhost:5173,http://localhost:5174` | Allowed CORS origins                                                                                                                                                                                                                                                                                                                                                     |
| `LOG_LEVEL`                          | `INFO`                                        | Logging level                                                                                                                                                                                                                                                                                                                                                            |
| `HEADLESS`                           | `false`                                       | `true` runs the browser invisibly (CI, Docker)                                                                                                                                                                                                                                                                                                                           |
| `BROWSER_CHANNEL`                    | `chrome`                                      | Use the installed Google Chrome; empty string falls back to bundled Chromium (also the automatic fallback if Chrome is missing)                                                                                                                                                                                                                                          |
| `SLOW_MO_MS`                         | `250`                                         | Delay between actions so a headed run is watchable                                                                                                                                                                                                                                                                                                                       |
| `STEP_TIMEOUT_MS`                    | `15000`                                       | Per-step Playwright timeout                                                                                                                                                                                                                                                                                                                                              |
| `ELEMENT_READY_TIMEOUT_MS`           | `30000`                                       | How long a step keeps looking for an element it cannot find. Short on purpose: a step that has lost its element is not going to find it. Spent before the action, so the step timeout still measures the action itself                                                                                                                                                   |
| `ELEMENT_BUSY_TIMEOUT_MS`            | `180000`                                      | How long a step waits once the element is on screen but the app is holding it switched off — a composer locked while an answer streams in, a save button disabled until an upload finishes. That is the app working, so it is allowed to run into minutes; the run says every 15s that it is still waiting. Only ever spent when a locked element has actually been seen |
| `STEP_RETRY_ATTEMPTS`                | `2`                                           | Extra attempts for a step whose element never became actionable. Each one waits for the app to go quiet, looks the element up again and acts afresh. They share `ELEMENT_READY_TIMEOUT_MS` rather than adding to it; waiting out a busy app happens once, on the first attempt                                                                                           |
| `NAVIGATION_TIMEOUT_MS`              | `45000`                                       | Separate, larger budget for page loads — DNS, TLS and a cold redirect can outlast a step timeout on their own                                                                                                                                                                                                                                                            |
| `VIDEO`                              | `on`                                          | `on` films every run; `off` skips filming and relies on the screenshot replay                                                                                                                                                                                                                                                                                            |
| `VIEWPORT_WIDTH` / `VIEWPORT_HEIGHT` | `1440` / `900`                                | Browser window size                                                                                                                                                                                                                                                                                                                                                      |
| `JIRA_URL`                           | _(empty)_                                     | Jira base URL, e.g. `https://jira.yourcompany.com`                                                                                                                                                                                                                                                                                                                       |
| `JIRA_TOKEN`                         | _(empty)_                                     | Personal Access Token (Data Center) or API token (Cloud)                                                                                                                                                                                                                                                                                                                 |
| `JIRA_EMAIL`                         | _(empty)_                                     | Set for Jira Cloud, which wants basic auth; leave empty for the bearer flow                                                                                                                                                                                                                                                                                              |
| `JIRA_TEST_EXECUTION_TYPE`           | `Test Execution`                              | The issue type a project's Jira key must have                                                                                                                                                                                                                                                                                                                            |
| `JIRA_ATTACH_EVIDENCE`               | `true`                                        | Attach screenshots, logs, video and trace to the issue                                                                                                                                                                                                                                                                                                                   |
| `JIRA_MAX_ATTACHMENT_MB`             | `10`                                          | Files larger than this are skipped rather than failing the upload                                                                                                                                                                                                                                                                                                        |
| `JIRA_VERIFY_SSL`                    | `true`                                        | Set `false` only for an internal Jira with a private CA                                                                                                                                                                                                                                                                                                                  |
| `CONFLUENCE_URL`                     | _(empty)_                                     | Confluence server URL                                                                                                                                                                                                                                                                                                                                                    |
| `CONFLUENCE_TOKEN`                   | _(empty)_                                     | Confluence API token                                                                                                                                                                                                                                                                                                                                                     |
| `BITBUCKET_URL`                      | _(empty)_                                     | Bitbucket server URL                                                                                                                                                                                                                                                                                                                                                     |
| `BITBUCKET_TOKEN`                    | _(empty)_                                     | Bitbucket API token                                                                                                                                                                                                                                                                                                                                                      |

---

## 📜 License

This project is a demo/PoC. All rights reserved.
