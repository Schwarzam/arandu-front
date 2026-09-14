# Arandu Portal

React/Tailwind portal and FastAPI service for the Arandu broker. Users sign in with their own ADSS credentials; passwords are never stored by the application.

## Run locally

1. Copy `.env.example` to `.env`, set the ADSS URL if necessary, and do not commit it.
2. Create a virtual environment and install the backend: `pip install -r backend/requirements.txt`.
3. Install frontend dependencies: `cd frontend && npm install`.
4. Run `./dev.sh`. Vite opens on port 5173 and proxies API calls to FastAPI on port 8000.

For production, copy `.env.example` to `.env` and run `./prod.sh`. Docker builds the React app, runs FastAPI privately, and exposes Nginx on **port 5001**. Nginx serves the SPA and proxies `/api` to FastAPI.

The API keeps only an opaque, HTTP-only session cookie in the browser; its in-memory session store is suitable for development. Replace it with Redis and a session TTL before multi-process production deployment.

The API executes its fixed, allow-listed portal queries through ADSS using the signed-in user's server-side token. It therefore respects that user's ADSS permissions and does not need a PostgreSQL password. FITS files remain stored by Arandu/Nginx; the API retrieves them and renders private cached PNG previews for the UI.
