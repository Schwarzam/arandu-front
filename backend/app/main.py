from __future__ import annotations

import asyncio
import math
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from astropy.io import fits
from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
import pyarrow.parquet as pq
from pydantic import BaseModel, Field

ADSS_BASE_URL = os.getenv("ADSS_BASE_URL", "https://ai-scope.cbpf.br").rstrip("/")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()]
DOCS_DIR = Path(os.getenv("DOCS_DIR", "docs")).resolve()

app = FastAPI(title="Arandu Portal", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# This intentionally contains tokens only, never user passwords.  Replace it
# with Redis (and a TTL) when deploying more than one API process.
sessions: dict[str, dict[str, Any]] = {}
# Calendar totals are kept after their first calculation so the same observing
# day is not re-aggregated on every dashboard visit. Use Redis in multi-worker
# production deployments.
calendar_cache: dict[tuple[str, str], dict[str, Any]] = {}
# Ranges currently being calculated. Keeping this separate prevents every
# browser refresh from submitting the same expensive ADSS request.
calendar_jobs: set[tuple[str, str, str]] = set()
# A failed range is attempted at most once per UTC day, rather than being
# repeatedly retried by every browser poll.
calendar_attempts: set[tuple[str, str, str, str]] = set()
MJD_EPOCH = date(1858, 11, 17)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=1024)


class ConeSearch(BaseModel):
    ra: float = Field(ge=0, lt=360)
    dec: float = Field(ge=-90, le=90)
    radius_arcsec: float = Field(gt=0, le=7200)
    limit: int = Field(default=100, ge=1, le=500)


def portal_session(arandu_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    if not arandu_session or arandu_session not in sessions:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in with ADSS.")
    return sessions[arandu_session]


async def adss_rows(session: dict[str, Any], query: str) -> list[dict[str, Any]]:
    """Run an allow-listed portal query as the signed-in ADSS user.

    The bearer token remains in this server-side session.  The browser sends
    only its opaque HttpOnly cookie, so a script injected into the page cannot
    steal an ADSS credential.
    """
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            result = await client.post(
                f"{ADSS_BASE_URL}/adss/sync",
                data={"query": query, "mode": "astroql"},
                headers={"Authorization": f"Bearer {session['token']}"},
            )
        if result.status_code in (401, 403):
            raise HTTPException(status_code=401, detail="Your ADSS session has expired. Please sign in again.")
        result.raise_for_status()
        return pq.read_table(BytesIO(result.content)).to_pylist()
    except HTTPException:
        raise
    except Exception as exc:
        # ADSS may return a query error, a transient error, or malformed data.
        # Keep the server response private while giving the UI an actionable status.
        raise HTTPException(status_code=502, detail="ADSS could not complete the data query.") from exc


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/login")
async def login(payload: LoginRequest, response: Response):
    # ADSS receives the submitted password over HTTPS. It is not logged,
    # persisted, or returned to the browser.
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            auth = await client.post(
                f"{ADSS_BASE_URL}/adss/v1/auth/login",
                data={"username": payload.username, "password": payload.password},
            )
            if auth.status_code in (401, 403):
                raise HTTPException(status_code=401, detail="Invalid ADSS username or password.")
            auth.raise_for_status()
            token = auth.json().get("access_token")
            if not token:
                raise HTTPException(status_code=502, detail="ADSS did not return an access token.")
            me = await client.get(f"{ADSS_BASE_URL}/adss/v1/users/me", headers={"Authorization": f"Bearer {token}"})
            me.raise_for_status()
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach ADSS.") from exc

    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = {"token": token, "user": me.json()}
    response.set_cookie("arandu_session", session_id, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=8 * 3600, path="/")
    return {"user": me.json()}


@app.post("/api/auth/logout", status_code=204)
def logout(response: Response, arandu_session: str | None = Cookie(default=None)):
    if arandu_session:
        sessions.pop(arandu_session, None)
    response.delete_cookie("arandu_session", path="/")


@app.get("/api/auth/me")
def me(session: dict[str, Any] = Depends(portal_session)):
    return {"user": session["user"]}


def documentation_file(relative_path: str) -> Path:
    candidate = (DOCS_DIR / relative_path).resolve()
    if not candidate.is_relative_to(DOCS_DIR) or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Documentation file not found.")
    return candidate


@app.get("/api/docs")
def documentation_index():
    if not DOCS_DIR.exists():
        return {"documents": []}
    documents = []
    for file in sorted(DOCS_DIR.rglob("*.md")):
        relative = file.relative_to(DOCS_DIR).as_posix()
        title = next((line.removeprefix("# ").strip() for line in file.read_text(encoding="utf-8").splitlines() if line.startswith("# ")), file.stem.replace("-", " ").title())
        documents.append({"path": relative, "title": title, "section": str(Path(relative).parent) if Path(relative).parent != Path(".") else "General"})
    return {"documents": documents}


@app.get("/api/docs/{document_path:path}")
def documentation_page(document_path: str):
    file = documentation_file(document_path)
    if file.suffix.lower() != ".md":
        raise HTTPException(status_code=404, detail="Documentation page not found.")
    return {"path": document_path, "markdown": file.read_text(encoding="utf-8")}


@app.get("/api/docs-assets/{asset_path:path}")
def documentation_asset(asset_path: str):
    return FileResponse(documentation_file(asset_path), headers={"Cache-Control": "public, max-age=3600"})


async def refresh_calendar_range(subject: str, session: dict[str, Any], start: date, end: date) -> None:
    """Populate a day's cache off-request using portable AstroQL syntax.

    AstroQL deployments do not consistently support SQL casts, FLOOR, or
    COUNT(DISTINCT). Fetching the two required columns and binning locally is
    portable and means a query failure never breaks the calendar endpoint.
    """
    job = (subject, start.isoformat(), end.isoformat())
    try:
        first_mjd, last_mjd = (start - MJD_EPOCH).days, (end - MJD_EPOCH).days
        rows = await adss_rows(session, f"""
            SELECT midpoint_mjd_tai, dia_object_id
            FROM arandu.dia_source
            WHERE midpoint_mjd_tai >= {first_mjd}
              AND midpoint_mjd_tai < {last_mjd}
        """)
        totals: dict[str, dict[str, Any]] = {}
        for row in rows:
            try:
                key = (MJD_EPOCH + timedelta(days=math.floor(float(row["midpoint_mjd_tai"])))).isoformat()
                bucket = totals.setdefault(key, {"detections": 0, "objects": set()})
                bucket["detections"] += 1
                bucket["objects"].add(row["dia_object_id"])
            except (KeyError, TypeError, ValueError):
                continue
        computed_on = datetime.now(timezone.utc).date().isoformat()
        for offset in range((end - start).days):
            key = (start + timedelta(days=offset)).isoformat()
            bucket = totals.get(key, {"detections": 0, "objects": set()})
            calendar_cache[(subject, key)] = {"computed_on": computed_on, "value": {"day": key, "objects": len(bucket["objects"]), "detections": bucket["detections"]}}
    except HTTPException:
        # Retain a prior completed value. The browser will retry tomorrow or
        # when the range is requested again; it never receives this failure.
        pass
    finally:
        calendar_jobs.discard(job)


@app.get("/api/calendar")
async def calendar(start: date = Query(...), end: date = Query(...), session: dict[str, Any] = Depends(portal_session)):
    if end <= start or end - start > timedelta(days=370):
        raise HTTPException(status_code=422, detail="Choose a range from one to 370 days.")
    subject = str(session["user"].get("id") or session["user"].get("username") or "unknown")
    requested_days = [start + timedelta(days=offset) for offset in range((end - start).days)]
    computed_on = datetime.now(timezone.utc).date().isoformat()
    stale = any(calendar_cache.get((subject, day.isoformat()), {}).get("computed_on") != computed_on for day in requested_days)
    job = (subject, start.isoformat(), end.isoformat())
    attempt = (*job, computed_on)
    if stale and job not in calendar_jobs and attempt not in calendar_attempts:
        calendar_jobs.add(job)
        calendar_attempts.add(attempt)
        asyncio.create_task(refresh_calendar_range(subject, {"token": session["token"]}, start, end))
    return {"start": start, "end": end, "pending": job in calendar_jobs, "days": [calendar_cache.get((subject, day.isoformat()), {"value": {"day": day.isoformat(), "objects": 0, "detections": 0}})["value"] for day in requested_days]}


@app.post("/api/search/cone")
async def cone_search(payload: ConeSearch, session: dict[str, Any] = Depends(portal_session)):
    radius_deg = payload.radius_arcsec / 3600.0
    result = await adss_rows(session, f"""
        SELECT TOP {payload.limit} o.dia_object_id, o.ra, o.dec, o.n_dia_sources,
               o.first_dia_source_mjd_tai, o.last_dia_source_mjd_tai
        FROM arandu.dia_object AS o
        WHERE cone(o.ra, o.dec, {payload.ra}, {payload.dec}, {radius_deg})
    """)
    # AstroQL's cone predicate stays index-friendly.  Compute display-only
    # angular separations locally so this works across ADSS deployments.
    ra0, dec0 = np.deg2rad([payload.ra, payload.dec])
    for item in result:
        ra, dec = np.deg2rad([float(item["ra"]), float(item["dec"])])
        cosine = np.sin(dec0) * np.sin(dec) + np.cos(dec0) * np.cos(dec) * np.cos(ra - ra0)
        item["separation_arcsec"] = float(np.rad2deg(np.arccos(np.clip(cosine, -1, 1))) * 3600)
    result.sort(key=lambda item: item["separation_arcsec"])
    return {"objects": result}


@app.get("/api/objects/{object_id}")
async def object_detail(object_id: int, session: dict[str, Any] = Depends(portal_session)):
    object_rows = await adss_rows(session, f"SELECT * FROM arandu.dia_object WHERE dia_object_id = {object_id}")
    if not object_rows:
        raise HTTPException(status_code=404, detail="Object not found.")
    source_rows = await adss_rows(session, f"""
        SELECT TOP 10000 s.dia_source_id, s.midpoint_mjd_tai, s.ra, s.dec, s.band,
               s.psf_flux, s.psf_flux_err, s.snr, s.reliability,
               a.cutout_science, a.cutout_template, a.cutout_difference
        FROM arandu.dia_source s LEFT JOIN arandu.alert a USING (dia_source_id)
        WHERE s.dia_object_id = {object_id} ORDER BY s.midpoint_mjd_tai
    """)
    return {"object": object_rows[0], "sources": source_rows}


@app.get("/api/cutouts/{source_id}/{kind}.png")
async def cutout(source_id: int, kind: str, session: dict[str, Any] = Depends(portal_session)):
    columns = {"science": "cutout_science", "template": "cutout_template", "difference": "cutout_difference"}
    if kind not in columns:
        raise HTTPException(status_code=404, detail="Unknown cutout type.")
    found = await adss_rows(session, f"SELECT {columns[kind]} AS url FROM arandu.alert WHERE dia_source_id = {source_id}")
    if not found or not found[0]["url"]:
        raise HTTPException(status_code=404, detail="Cutout unavailable.")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            image_response = await client.get(found[0]["url"])
            image_response.raise_for_status()
        with fits.open(BytesIO(image_response.content), memmap=False) as hdul:
            data = np.asarray(hdul[0].data, dtype=np.float32).squeeze()
        valid = data[np.isfinite(data)]
        if data.ndim != 2 or not valid.size:
            raise ValueError("cutout has no usable 2D image")
        lo, hi = np.percentile(valid, (1, 99))
        scaled = np.zeros(data.shape, dtype=np.uint8) if hi <= lo else np.clip((data - lo) * 255 / (hi - lo), 0, 255).astype(np.uint8)
        output = BytesIO(); Image.fromarray(scaled).save(output, format="PNG", optimize=True)
        return Response(output.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
    except (httpx.HTTPError, OSError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Could not render this FITS cutout.") from exc
