"""FastAPI backend: share a video link -> poll job -> download .rtk.

Run:  uvicorn api:app --host 0.0.0.0 --port $PORT

Env vars:
  GEMINI_API_KEY   default Gemini key (a client may override per request with X-Gemini-Key)
  GEMINI_MODEL     optional model override
  APP_TOKEN        shared bearer token (>= 16 chars) -> user "owner"
  APP_TOKENS       optional "alice:token1,bob:token2" for per-user access
  WEBSHARE_PROXY_USERNAME / WEBSHARE_PROXY_PASSWORD   optional residential proxy
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

import pipeline
from auth import EnvTokenStore, TokenStore, User, parse_bearer
from extractor import DEFAULT_MODEL

JOB_TTL_SECONDS = 30 * 60
MAX_JOBS_PER_USER = 20
MAX_CONCURRENT_JOBS = 2  # free tier has little RAM; reels are buffered in memory

app = FastAPI(title="Video to RecetteTek", version="1.0")
_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS)
_lock = threading.Lock()


# ----------------------------------------------------------------- auth
_store: TokenStore | None = None


def get_store() -> TokenStore:
    global _store
    if _store is None:
        _store = EnvTokenStore()
    return _store


def current_user(authorization: Optional[str] = Header(default=None)) -> User:
    token = parse_bearer(authorization)
    user = get_store().resolve(token) if token else None
    if user is None:
        raise HTTPException(401, "Invalid or missing bearer token",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


# ----------------------------------------------------------------- jobs
@dataclass
class Job:
    id: str
    user_id: str
    status: str = "queued"  # queued | running | done | error
    created: float = field(default_factory=time.time)
    error: str | None = None
    title: str | None = None
    source: str | None = None
    recipe: dict | None = None
    filename: str | None = None
    rtk: bytes | None = None


_jobs: dict[str, Job] = {}


def _purge() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    for jid in [j.id for j in _jobs.values() if j.created < cutoff]:
        _jobs.pop(jid, None)


def _run_job(job: Job, text: str, api_key: str, model: str, languages: list[str],
             transcript: str | None) -> None:
    job.status = "running"
    try:
        result = pipeline.run_pipeline(
            text, api_key=api_key, model=model, languages=languages, transcript=transcript,
            webshare_username=os.environ.get("WEBSHARE_PROXY_USERNAME"),
            webshare_password=os.environ.get("WEBSHARE_PROXY_PASSWORD"),
        )
        job.filename, job.rtk = pipeline.build_rtk_file(result)
        job.title, job.source, job.recipe = result.title, result.source, result.data
        job.status = "done"
    except Exception as e:  # report any failure to the client, never crash the worker
        job.error = f"{type(e).__name__}: {e}"[:500]
        job.status = "error"


def _get_job(job_id: str, user: User) -> Job:
    job = _jobs.get(job_id)
    # 404 (not 403) for other users' jobs so ids can't be probed
    if job is None or job.user_id != user.id:
        raise HTTPException(404, "Job not found")
    return job


# ----------------------------------------------------------------- schemas
class CreateJob(BaseModel):
    text: str = Field(description="A video link, or arbitrary shared text containing one")
    languages: list[str] = Field(default_factory=lambda: ["en"])
    transcript: Optional[str] = Field(default=None, description="Manual transcript (YouTube only)")


class JobStatus(BaseModel):
    id: str
    status: str
    error: Optional[str] = None
    title: Optional[str] = None
    source: Optional[str] = None
    recipe: Optional[dict] = None
    download_path: Optional[str] = None


def _view(job: Job) -> JobStatus:
    return JobStatus(id=job.id, status=job.status, error=job.error, title=job.title,
                     source=job.source, recipe=job.recipe,
                     download_path=f"/v1/jobs/{job.id}/rtk" if job.status == "done" else None)


# ----------------------------------------------------------------- routes
@app.get("/health")
def health() -> dict:
    """Unauthenticated; apps ping this to wake a sleeping free-tier instance."""
    return {"ok": True}


@app.post("/v1/jobs", response_model=JobStatus, status_code=202)
def create_job(body: CreateJob, user: User = Depends(current_user),
               x_gemini_key: Optional[str] = Header(default=None)) -> JobStatus:
    api_key = (x_gemini_key or "").strip() or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise HTTPException(503, "Server has no Gemini key; send one in the X-Gemini-Key header")
    if pipeline.extract_first_url(body.text) is None:
        raise HTTPException(422, "No video link found in the text")
    with _lock:
        _purge()
        if sum(1 for j in _jobs.values() if j.user_id == user.id) >= MAX_JOBS_PER_USER:
            raise HTTPException(429, "Too many recent jobs; try again in a few minutes")
        job = Job(id=uuid.uuid4().hex, user_id=user.id)
        _jobs[job.id] = job
    _executor.submit(_run_job, job, body.text, api_key,
                     os.environ.get("GEMINI_MODEL", DEFAULT_MODEL), body.languages, body.transcript)
    return _view(job)


@app.get("/v1/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str, user: User = Depends(current_user)) -> JobStatus:
    return _view(_get_job(job_id, user))


@app.get("/v1/jobs/{job_id}/rtk")
def download_rtk(job_id: str, user: User = Depends(current_user)) -> Response:
    job = _get_job(job_id, user)
    if job.status != "done" or job.rtk is None:
        raise HTTPException(409, f"Job is {job.status}")
    return Response(
        content=job.rtk, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{job.filename}"'},
    )
