# Arandu Portal

React/Tailwind portal and FastAPI service for the Arandu broker. It uses ADSS's public query interface, so visitors can explore the portal without signing in.

## Run locally

1. Copy `.env.example` to `.env`, set the ADSS URL and `MONITOR_HISTORY_PATH` if necessary, and do not commit it.
2. Create a virtual environment and install the backend: `pip install -r backend/requirements.txt`.
3. Install frontend dependencies: `cd frontend && npm install`.
4. Run `./dev.sh`. Vite opens on port 5173 and proxies API calls to FastAPI on port 8000.

For production, copy `.env.example` to `.env` and run `./prod.sh`. Docker builds the React app, runs FastAPI privately, and exposes Nginx on **port 5001**. Nginx serves the SPA, serves cutout FITS files from `/home/astrodados4/arandu/data/cutouts` at `/cutouts/`, and proxies `/api` to FastAPI. Cutouts must be arranged as `<dia_source_id>/<science|template|difference>.fits`. The API mounts the monitor log read-only and uses `/monitor-data/monitor-history.jsonl` in the container; set `MONITOR_HISTORY_PATH` only when that container path changes.

The portal uses ADSS's public query interface and does not require a browser login or service credentials. The calendar cache is refreshed at startup and once per UTC day. `CALENDAR_CACHE_LOOKBACK_DAYS` controls the rolling historical window (370 days by default).

The API executes its fixed, allow-listed portal queries through ADSS's public interface and does not need a PostgreSQL password. FITS cutouts are served directly by Nginx and rendered in the browser, avoiding an ADSS lookup and server-side conversion for every image.
