# Arandu Portal

React/Tailwind portal and FastAPI service for the Arandu broker. Users sign in with their own ADSS credentials; passwords are never stored by the application.

## Run locally

1. Copy `.env.example` to `.env`, set the ADSS URL and `MONITOR_HISTORY_PATH` if necessary, and do not commit it.
2. Create a virtual environment and install the backend: `pip install -r backend/requirements.txt`.
3. Install frontend dependencies: `cd frontend && npm install`.
4. Run `./dev.sh`. Vite opens on port 5173 and proxies API calls to FastAPI on port 8000.

For production, copy `.env.example` to `.env` and run `./prod.sh`. Docker builds the React app, runs FastAPI privately, and exposes Nginx on **port 5001**. Nginx serves the SPA, serves cutout FITS files from `/home/astrodados4/arandu/data/cutouts` at `/cutouts/`, and proxies `/api` to FastAPI. Cutouts must be arranged as `<dia_source_id>/<science|template|difference>.fits`. The API mounts the monitor log read-only and uses `/monitor-data/monitor-history.jsonl` in the container; set `MONITOR_HISTORY_PATH` only when that container path changes.

The API keeps only an opaque, HTTP-only session cookie in the browser; its in-memory session store is suitable for development. Replace it with Redis and a session TTL before multi-process production deployment. Set `ADSS_SERVICE_USERNAME` and `ADSS_SERVICE_PASSWORD` to a read-only ADSS account in production: the API logs in with those credentials at each refresh, uses the newly-issued token to update the shared calendar cache at startup and then once per UTC day, and does not retain that token. `CALENDAR_CACHE_LOOKBACK_DAYS` controls the rolling historical window (370 days by default).

The API executes its fixed, allow-listed portal queries through ADSS using the signed-in user's server-side token. It therefore respects that user's ADSS permissions and does not need a PostgreSQL password. FITS cutouts are served directly by Nginx and rendered in the browser, avoiding an ADSS lookup and server-side conversion for every image; Nginx first verifies the existing portal session.
