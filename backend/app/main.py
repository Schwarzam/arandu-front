from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import logging
import os
import re
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
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image
import pyarrow.parquet as pq
from pydantic import BaseModel, Field

ADSS_BASE_URL = os.getenv("ADSS_BASE_URL", "https://ai-scope.cbpf.br").rstrip("/")
ADSS_SERVICE_USERNAME = os.getenv("ADSS_SERVICE_USERNAME")
ADSS_SERVICE_PASSWORD = os.getenv("ADSS_SERVICE_PASSWORD")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()]
DOCS_DIR = Path(os.getenv("DOCS_DIR", "docs")).resolve()
CALENDAR_CACHE_LOOKBACK_DAYS = int(os.getenv("CALENDAR_CACHE_LOOKBACK_DAYS", "370"))

# This intentionally contains tokens only, never user passwords.  Replace it
# with Redis (and a TTL) when deploying more than one API process.
sessions: dict[str, dict[str, Any]] = {}
# Calendar totals belong to the server, not an individual browser session.
# Deploy Redis or another shared cache when using more than one API process.
calendar_cache: dict[str, dict[str, Any]] = {}
calendar_jobs: set[tuple[str, str]] = set()
calendar_runner_task: asyncio.Task[None] | None = None
MJD_EPOCH = date(1858, 11, 17)
logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    global calendar_runner_task
    if ADSS_SERVICE_USERNAME and ADSS_SERVICE_PASSWORD:
        calendar_runner_task = asyncio.create_task(run_calendar_refresh_loop())
    yield
    if calendar_runner_task:
        calendar_runner_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await calendar_runner_task


app = FastAPI(title="Arandu Portal", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=1024)


class ConeSearch(BaseModel):
    ra: float = Field(ge=0, lt=360)
    dec: float = Field(ge=-90, le=90)
    radius_arcsec: float = Field(gt=0, le=7200)
    limit: int = Field(default=100, ge=1, le=500)


class DiscoverySearch(BaseModel):
    query: str = Field(min_length=1, max_length=256)
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


async def adss_service_session() -> dict[str, str]:
    """Log in the calendar worker and return a newly-issued ADSS token."""
    if not ADSS_SERVICE_USERNAME or not ADSS_SERVICE_PASSWORD:
        raise RuntimeError("ADSS service credentials are not configured")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{ADSS_BASE_URL}/adss/v1/auth/login",
                data={"username": ADSS_SERVICE_USERNAME, "password": ADSS_SERVICE_PASSWORD},
            )
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise RuntimeError("ADSS service login returned no access token")
        return {"token": token}
    except httpx.HTTPError as exc:
        raise RuntimeError("ADSS service login failed") from exc


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
    return JSONResponse(content={"documents": documents}, headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/api/docs/{document_path:path}")
def documentation_page(document_path: str):
    file = documentation_file(document_path)
    if file.suffix.lower() != ".md":
        raise HTTPException(status_code=404, detail="Documentation page not found.")
    return JSONResponse(content={"path": document_path, "markdown": file.read_text(encoding="utf-8")}, headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/api/docs-assets/{asset_path:path}")
def documentation_asset(asset_path: str):
    return FileResponse(documentation_file(asset_path), headers={"Cache-Control": "no-store, max-age=0"})


async def refresh_calendar_range(session: dict[str, Any], start: date, end: date) -> None:
    """Populate cached daily detection totals without fetching every source.

    A count is issued for each UTC day so its range predicate can use the
    ``dia_source.midpoint_mjd_tai`` index.  This avoids the former query which
    transferred every source in a month and then counted them in this process.
    AstroQL's aggregate support is portable; date truncation and DISTINCT are
    not, so object totals are deliberately not computed here.
    """
    job = (start.isoformat(), end.isoformat())
    if job in calendar_jobs:
        return
    calendar_jobs.add(job)
    try:
        computed_on = datetime.now(timezone.utc).date().isoformat()
        semaphore = asyncio.Semaphore(8)

        async def refresh_day(day: date) -> None:
            key = day.isoformat()
            if calendar_cache.get(key, {}).get("computed_on") == computed_on:
                return
            first_mjd, last_mjd = (day - MJD_EPOCH).days, (day + timedelta(days=1) - MJD_EPOCH).days
            try:
                async with semaphore:
                    rows = await adss_rows(session, f"""
                        SELECT COUNT(dia_source.midpoint_mjd_tai) AS detections
                        FROM arandu.dia_source
                        WHERE midpoint_mjd_tai >= {first_mjd}
                          AND midpoint_mjd_tai < {last_mjd}
                    """)
                count = int(rows[0]["detections"]) if rows else 0
                calendar_cache[key] = {
                    "computed_on": computed_on,
                    "value": {"day": key, "detections": count},
                }
            except (HTTPException, KeyError, TypeError, ValueError):
                # Keep a prior completed value if this individual day fails.
                # One bad query must not prevent the rest of a range caching.
                return

        await asyncio.gather(*(refresh_day(start + timedelta(days=offset)) for offset in range((end - start).days)))
    finally:
        calendar_jobs.discard(job)


async def calendar_detection_count(session: dict[str, Any], day: date) -> int:
    """Return the current detection count for one UTC calendar day."""
    first_mjd = (day - MJD_EPOCH).days
    last_mjd = (day + timedelta(days=1) - MJD_EPOCH).days
    rows = await adss_rows(session, f"""
        SELECT COUNT(dia_source.midpoint_mjd_tai) AS detections
        FROM arandu.dia_source
        WHERE midpoint_mjd_tai >= {first_mjd}
          AND midpoint_mjd_tai < {last_mjd}
    """)
    return int(rows[0]["detections"]) if rows else 0


async def run_calendar_refresh_loop() -> None:
    """Refresh the server-wide calendar cache once per UTC day with a fresh token."""
    while True:
        today = datetime.now(timezone.utc).date()
        try:
            await refresh_calendar_range(
                await adss_service_session(),
                today - timedelta(days=CALENDAR_CACHE_LOOKBACK_DAYS),
                today + timedelta(days=1),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Daily calendar cache refresh failed")
        now = datetime.now(timezone.utc)
        next_run = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        await asyncio.sleep(max((next_run - now).total_seconds(), 1))


@app.get("/api/calendar")
async def calendar(start: date = Query(...), end: date = Query(...), session: dict[str, Any] = Depends(portal_session)):
    if end <= start or end - start > timedelta(days=370):
        raise HTTPException(status_code=422, detail="Choose a range from one to 370 days.")
    requested_days = [start + timedelta(days=offset) for offset in range((end - start).days)]
    pending = bool(calendar_jobs) and any(day.isoformat() not in calendar_cache for day in requested_days)
    today = datetime.now(timezone.utc).date()
    days = [calendar_cache.get(day.isoformat(), {"value": {"day": day.isoformat(), "detections": 0}})["value"] for day in requested_days]

    # Today's observations continue arriving after the daily cache is built.
    # Replace only that entry with a live aggregate so the highlighted cell
    # always reflects the current ADSS result for the signed-in user.
    if today in requested_days:
        try:
            today_index = requested_days.index(today)
            days[today_index] = {"day": today.isoformat(), "detections": await calendar_detection_count(session, today)}
        except (HTTPException, KeyError, TypeError, ValueError):
            # An unavailable live query should not take the calendar down; the
            # last completed cache value remains the useful fallback.
            pass

    return {"start": start, "end": end, "pending": pending, "days": days}


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


def object_ids_from_rows(rows: list[dict[str, Any]]) -> list[int]:
    """Keep source-query object ids in their time-ranked order."""
    return list(dict.fromkeys(int(row["dia_object_id"]) for row in rows if row.get("dia_object_id") is not None))


def enrichment_label(value: Any) -> str | None:
    if isinstance(value, dict) and value.get("label") is not None:
        return str(value["label"])
    return None


async def objects_by_ids(session: dict[str, Any], object_ids: list[int]) -> list[dict[str, Any]]:
    if not object_ids:
        return []
    identifiers = ", ".join(str(item) for item in object_ids)
    rows = await adss_rows(session, f"""
        SELECT dia_object_id, ra, dec, n_dia_sources, first_dia_source_mjd_tai, last_dia_source_mjd_tai
        FROM arandu.dia_object WHERE dia_object_id IN ({identifiers})
    """)
    by_id = {int(row["dia_object_id"]): row for row in rows}
    return [by_id[item] for item in object_ids if item in by_id]


@app.post("/api/search/discovery")
async def discovery_search(payload: DiscoverySearch, session: dict[str, Any] = Depends(portal_session)):
    """Search objects through a concise, allow-listed discovery language."""
    query = payload.query.strip()
    cone_match = re.fullmatch(r"(?:cone:\s*)?([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)(?:\s*/\s*(\d+(?:\.\d+)?))?", query, flags=re.IGNORECASE)
    if cone_match:
        ra, dec, radius, divisor = (float(value) if value is not None else None for value in cone_match.groups())
        radius_arcsec = radius / (divisor or 1)
        if not 0 <= ra < 360 or not -90 <= dec <= 90 or not 0 < radius_arcsec <= 7200:
            raise HTTPException(status_code=422, detail="Use RA 0–360, Dec −90–90, and a radius up to 7200 arcsec.")
        return await cone_search(ConeSearch(ra=ra, dec=dec, radius_arcsec=radius_arcsec, limit=payload.limit), session)

    directive_pattern = re.compile(r"(enricher|classification|last)\s*:\s*([A-Za-z0-9_.-]+)", flags=re.IGNORECASE)
    directives = {match.group(1).lower(): match.group(2) for match in directive_pattern.finditer(query)}
    if directives and not directive_pattern.sub("", query).strip():
        if len(directives) != len(list(directive_pattern.finditer(query))):
            raise HTTPException(status_code=422, detail="Use each search filter at most once.")
        last_value = directives.get("last")
        if last_value is not None and not last_value.isdecimal():
            raise HTTPException(status_code=422, detail="The number after last: must be an integer.")
        count = min(int(last_value) if last_value is not None else payload.limit, payload.limit)
        if count < 1:
            raise HTTPException(status_code=422, detail="The number after last: must be at least one.")
        enricher = directives.get("enricher")
        classification = directives.get("classification")
        if not enricher and not classification:
            rows = await adss_rows(session, f"""
                SELECT TOP {count} dia_object_id FROM arandu.dia_source
                ORDER BY midpoint_mjd_tai DESC
            """)
            return {"objects": await objects_by_ids(session, object_ids_from_rows(rows)), "description": f"Newest {count} detections"}
        where = f"WHERE e.enricher_name = '{enricher}'" if enricher else ""
        rows = await adss_rows(session, f"""
            SELECT TOP {count * 40} s.dia_object_id, e.value
            FROM arandu.enrichment e JOIN arandu.dia_source s USING (dia_source_id)
            {where}
            ORDER BY s.midpoint_mjd_tai DESC
        """)
        matched_rows = [row for row in rows if classification is None or enrichment_label(row.get("value")) == classification]
        description = f"Objects enriched by {enricher}" if enricher else f"Objects classified as {classification}"
        if enricher and classification:
            description += f" · {classification}"
        if "last" in directives:
            description = f"Newest {count} matching observations · {description}"
        result_rows = matched_rows[:count] if "last" in directives else matched_rows
        return {"objects": await objects_by_ids(session, object_ids_from_rows(result_rows)[:payload.limit]), "description": description}

    raise HTTPException(status_code=422, detail="Try a cone such as 0.1 0.1 10/3600, enricher:<name>, classification:<label>, or last:<count>.")


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
    enrichment_rows = await adss_rows(session, f"""
        SELECT e.enrichment_id, e.dia_source_id, e.enricher_name, e.version,
               e.value, e.additionals, e.enriched_at
        FROM arandu.enrichment e JOIN arandu.dia_source s USING (dia_source_id)
        WHERE s.dia_object_id = {object_id}
        ORDER BY e.enriched_at DESC
    """)
    return {"object": object_rows[0], "sources": source_rows, "enrichments": enrichment_rows}


def cutout_bytes(value: Any) -> bytes:
    """Decode an alert cutout stored as a URL, data URI, or base64 FITS."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("cutout is empty")
    payload = value.strip()
    if payload.startswith(("http://", "https://")):
        raise ValueError("cutout URL must be fetched separately")
    if payload.startswith("data:"):
        try:
            return base64.b64decode(payload.split(",", 1)[1], validate=True)
        except (IndexError, binascii.Error) as exc:
            raise ValueError("cutout data URI is not valid base64") from exc
    try:
        return base64.b64decode(payload, validate=True)
    except binascii.Error as exc:
        raise ValueError("cutout is not a supported URL or base64 FITS payload") from exc


@app.get("/api/cutouts/{source_id}/{kind}.png")
async def cutout(source_id: int, kind: str, session: dict[str, Any] = Depends(portal_session)):
    columns = {"science": "cutout_science", "template": "cutout_template", "difference": "cutout_difference"}
    if kind not in columns:
        raise HTTPException(status_code=404, detail="Unknown cutout type.")
    found = await adss_rows(session, f"SELECT {columns[kind]} AS url FROM arandu.alert WHERE dia_source_id = {source_id}")
    if not found or not found[0]["url"]:
        raise HTTPException(status_code=404, detail="Cutout unavailable.")
    try:
        value = found[0]["url"]
        if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=20) as client:
                image_response = await client.get(value)
                image_response.raise_for_status()
            raw = image_response.content
        else:
            raw = cutout_bytes(value)
        with fits.open(BytesIO(raw), memmap=False) as hdul:
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
