# lt console (frontend)

React 19 + TypeScript + Tailwind CSS v4 web console for the `lt` load generator. Built
with Vite, React Router, TanStack Query and Recharts.

## Features

- **Dashboard** — run overview, pass rate, and live banner for the active run.
- **Auto scan** — paste a URL; the backend crawls it with Playwright, lists every API the
  pages call, and load-tests each one in turn with per-API verdicts.
- **New run** — YAML editor with bundled examples, file upload, CLI-equivalent overrides,
  debounced server-side validation, target-rate preview, and a confirmation guard.
- **Run detail** — live progress, throughput/latency charts (CO-safe latency), status
  codes, per-route totals, structured logs, artifact downloads, graceful/force stop.
- **Analysis** — sustained capacity, burst, capacity curve, fairness, rate-limit headers
  and window-semantics verdicts, re-runnable with custom expectations.
- **Demo server** — start/stop a local rate limiter and watch its counters.
- Light/dark/system themes, keyboard-accessible components, responsive layout.

## Development

```bash
# terminal 1 — API (from backend/)
lt serve                      # http://127.0.0.1:8000

# terminal 2 — UI (from frontend/)
npm ci
npm run dev                   # http://localhost:5173, proxies /api to :8000
```

Set `LT_API_PROXY_TARGET` (see [.env.example](.env.example)) to point the dev proxy at a
different API. If the API requires `LT_API_TOKEN`, the UI prompts for it and keeps it in
`sessionStorage` for the tab.

| Script                                                 | Purpose                                  |
| ------------------------------------------------------ | ---------------------------------------- |
| `npm run dev`                                          | Vite dev server with HMR                 |
| `npm run build`                                        | Type-check and build to `dist/`          |
| `npm run preview`                                      | Serve the production build locally       |
| `npm run typecheck` / `lint` / `format:check` / `test` | Quality gates (`npm run check` runs all) |

## Deployment

- **Single origin:** `lt serve --static-dir ../frontend/dist` serves the UI and API
  together.
- **Separate containers:** `docker build -t lt-frontend .` produces an unprivileged nginx
  image that serves the SPA and proxies `/api` to `LT_API_UPSTREAM`
  (default `http://backend:8000`). See the root [docker-compose.yml](../docker-compose.yml).
- **Different origins:** build with `VITE_API_BASE_URL=https://api.example.com` and set
  `LT_API_CORS_ORIGINS` on the backend.

## Structure

```
src/
  components/   UI primitives (ui/), layout, charts, analysis panel, editor
  hooks/        TanStack Query hooks, theme, debounce
  lib/          API client, types mirroring the backend schemas, formatters
  pages/        Route-level screens (lazy-loaded)
  test/         Vitest setup and helpers
```
