# lt — load testing & API rate-limit verification

Monorepo with two independently built and deployed parts:

| Folder | What | Stack |
|---|---|---|
| [backend/](backend) | `lt` CLI, load engine, limiter analysis, and REST API (`lt serve`) | Python 3.11+, httpx, FastAPI |
| [frontend/](frontend) | Web console for configuring, running, and analyzing tests | React 19, TypeScript, Tailwind CSS v4, Vite |

## Quickstart (local)

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
lt serve --port 8001                               # API on http://127.0.0.1:8001

# frontend (second terminal)
cd frontend
npm ci
npm run dev                                        # UI on http://localhost:5175
```

Ports differ from the standalone defaults so this tool can run alongside the Automation
Platform shell (5173) and the UI automation tool (5174 / 8000).

Open the UI, go to **Auto scan**, paste your app's URL, and press **Scan & load test**: a
headless browser (Playwright) discovers every API the app calls and load-tests each one.
You can also start the **Demo server** and create a **New run** from an example by hand.
The CLI keeps working as before (plus `lt scan URL`) — see
[backend/README.md](backend/README.md).

First-time setup for discovery: `playwright install chromium` (inside the backend venv).

## Production

```bash
LT_API_TOKEN=$(openssl rand -hex 32) docker compose up --build
# UI + API on http://localhost:8080 (enter the token when prompted)
```

- The backend refuses to bind a non-loopback address without `LT_API_TOKEN`.
- `LT_API_ALLOWED_HOSTS` restricts which targets any submitted config may load and which
  URLs may be scanned (defaults to loopback only); `LT_API_MAX_RPS_CAP` caps every run
  server-side.
- Alternatively serve both from one process: `npm run build` in `frontend/`, then
  `lt serve --static-dir ../frontend/dist`.

## Quality gates

```bash
cd backend && tools/check.sh           # ruff, black, mypy, pytest (+coverage)
cd frontend && npm run check           # tsc, eslint, prettier, vitest
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs both, builds the Python
wheel and the frontend bundle, and builds both Docker images.

## License

Apache-2.0 — see [LICENSE](LICENSE).
