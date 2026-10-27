# Vitt Guard dashboard

The React, TypeScript, and Vite dashboard reads real data from the Vitt Guard
API. It includes the overview, payment list and details, request inspector, and
an API Explorer for creating simulated payments. It does not include sample
data, and simulated payments do not move real money.

From PowerShell, install dependencies and start the development server with:

```powershell
npm.cmd install
npm.cmd run dev
```

The API client uses same-origin paths by default. For local Vite development,
the dev server proxies `/api` and `/health` to `http://127.0.0.1:8000`. To
override the backend address, create `frontend/.env.local`:

```dotenv
# Optional browser-visible API base URL; leave empty to use same-origin paths.
VITE_API_BASE_URL=

# Optional Vite development proxy target.
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
```

These settings contain no credentials. Never put database URLs, passwords, or
backend secrets in `VITE_*` variables because Vite exposes them to browser code.

The API Explorer sends real requests to the configured API. It retains the
exact key and payload for an explicit retry, reports HTTP 200 as an idempotency
replay and HTTP 201 as a newly created payment, and uses the returned request
ID to inspect the persisted request log. A timeout or connection failure is
shown as an unknown operation result; the Explorer never retries automatically
or generates a replacement key. Its copied cURL example is PowerShell syntax
using `curl.exe`; URL credentials, query parameters, and fragments are omitted.

Run frontend checks from this directory:

```powershell
npm.cmd run lint
npm.cmd run format:check
npm.cmd run typecheck
npm.cmd test -- --pool=threads --maxWorkers=1 --fileParallelism=false
npm.cmd run build
```

See the repository's root README for backend and PostgreSQL setup.
