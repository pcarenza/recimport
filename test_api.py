import threading
import time

import pytest
from fastapi.testclient import TestClient

import api
import pipeline

OWNER = "a" * 20
ALICE = "b" * 20
BOB = "c" * 20
FAKE_BYTES = b"fake-rtk-bytes"
URL_TEXT = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def auth(token=OWNER):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("APP_TOKEN", OWNER)
    monkeypatch.setenv("APP_TOKENS", f"alice:{ALICE},bob:{BOB}")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(api, "_store", None)
    api._jobs.clear()
    yield
    api._jobs.clear()
    api._store = None


@pytest.fixture
def client():
    return TestClient(api.app)


@pytest.fixture
def calls(monkeypatch):
    """Patch pipeline with fakes; records run_pipeline kwargs."""
    recorded = []

    def fake_run(text, **kw):
        recorded.append({"text": text, **kw})
        return pipeline.PipelineResult(
            data={"name": "Soup"}, canonical_url="https://example.com/v",
            thumbnail=None, source="youtube", title="Tasty Soup")

    monkeypatch.setattr(api.pipeline, "run_pipeline", fake_run)
    monkeypatch.setattr(api.pipeline, "build_rtk_file",
                        lambda result: ("Tasty_Soup.rtk", FAKE_BYTES))
    return recorded


def wait_job(client, job_id, token=OWNER, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/v1/jobs/{job_id}", headers=auth(token))
        assert r.status_code == 200
        if r.json()["status"] in ("done", "error"):
            return r.json()
        time.sleep(0.02)
    raise AssertionError("job did not finish in time")


def submit(client, token=OWNER, **body):
    body.setdefault("text", URL_TEXT)
    return client.post("/v1/jobs", json=body, headers=auth(token))


def test_health_open(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer " + "z" * 20},
    {"Authorization": OWNER},
    {"Authorization": "Basic " + OWNER},
    {"Authorization": "Bearer"},
    {"Authorization": "Bearer "},
])
def test_auth_required(client, calls, headers):
    assert client.post("/v1/jobs", json={"text": URL_TEXT}, headers=headers).status_code == 401
    assert client.get("/v1/jobs/abc", headers=headers).status_code == 401
    assert client.get("/v1/jobs/abc/rtk", headers=headers).status_code == 401
    assert calls == []


def test_happy_path(client, calls):
    r = submit(client)
    assert r.status_code == 202
    job_id = r.json()["id"]
    assert job_id
    body = wait_job(client, job_id)
    assert body["status"] == "done"
    assert body["title"] == "Tasty Soup"
    assert body["source"] == "youtube"
    assert body["recipe"] == {"name": "Soup"}
    assert body["download_path"] == f"/v1/jobs/{job_id}/rtk"

    d = client.get(body["download_path"], headers=auth())
    assert d.status_code == 200
    assert d.content == FAKE_BYTES
    assert d.headers["content-type"].startswith("application/octet-stream")
    cd = d.headers["content-disposition"]
    assert cd.startswith("attachment")
    assert cd.endswith('.rtk"')


def test_error_path(client, monkeypatch):
    def boom(text, **kw):
        raise ValueError("boom")

    monkeypatch.setattr(api.pipeline, "run_pipeline", boom)
    job_id = submit(client).json()["id"]
    body = wait_job(client, job_id)
    assert body["status"] == "error"
    assert "boom" in body["error"]
    assert body["download_path"] is None
    assert client.get(f"/v1/jobs/{job_id}/rtk", headers=auth()).status_code == 409


def test_unknown_job_404(client):
    assert client.get("/v1/jobs/nope", headers=auth()).status_code == 404
    assert client.get("/v1/jobs/nope/rtk", headers=auth()).status_code == 404


def test_user_isolation(client, calls):
    job_id = submit(client, OWNER).json()["id"]
    wait_job(client, job_id)
    assert client.get(f"/v1/jobs/{job_id}", headers=auth(ALICE)).status_code == 404
    assert client.get(f"/v1/jobs/{job_id}/rtk", headers=auth(ALICE)).status_code == 404
    assert client.get(f"/v1/jobs/{job_id}/rtk", headers=auth(OWNER)).status_code == 200


def test_named_user_can_use_own_job(client, calls):
    job_id = submit(client, ALICE).json()["id"]
    assert wait_job(client, job_id, ALICE)["status"] == "done"
    assert client.get(f"/v1/jobs/{job_id}", headers=auth(BOB)).status_code == 404


def test_no_link_422(client, calls):
    r = submit(client, text="just some words, no link")
    assert r.status_code == 422
    assert calls == []


def test_missing_text_422(client, calls):
    r = client.post("/v1/jobs", json={}, headers=auth())
    assert r.status_code == 422


def test_no_gemini_key_503(client, calls, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    assert submit(client).status_code == 503
    assert calls == []


def test_header_gemini_key_used(client, calls, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    r = client.post("/v1/jobs", json={"text": URL_TEXT},
                    headers={**auth(), "X-Gemini-Key": "client-key"})
    assert r.status_code == 202
    wait_job(client, r.json()["id"])
    assert calls[0]["api_key"] == "client-key"


def test_env_gemini_key_used_by_default(client, calls):
    wait_job(client, submit(client).json()["id"])
    assert calls[0]["api_key"] == "k"


def test_header_key_overrides_env(client, calls):
    r = client.post("/v1/jobs", json={"text": URL_TEXT},
                    headers={**auth(), "X-Gemini-Key": "client-key"})
    wait_job(client, r.json()["id"])
    assert calls[0]["api_key"] == "client-key"


def test_shared_text_passed_unchanged(client, calls):
    text = "Look at this https://fb.watch/abc/ yum"
    r = submit(client, text=text)
    assert r.status_code == 202
    wait_job(client, r.json()["id"])
    assert calls[0]["text"] == text


def test_languages_and_transcript_forwarded(client, calls):
    r = submit(client, languages=["fr", "en"], transcript="hello transcript")
    wait_job(client, r.json()["id"])
    assert calls[0]["languages"] == ["fr", "en"]
    assert calls[0]["transcript"] == "hello transcript"


def test_defaults_languages_en_no_transcript(client, calls):
    wait_job(client, submit(client).json()["id"])
    assert calls[0]["languages"] == ["en"]
    assert calls[0]["transcript"] is None


def test_max_jobs_per_user_429(client, monkeypatch):
    monkeypatch.setattr(api, "MAX_JOBS_PER_USER", 2)
    release = threading.Event()

    def blocking(text, **kw):
        release.wait(10)
        raise ValueError("released")

    monkeypatch.setattr(api.pipeline, "run_pipeline", blocking)
    try:
        assert submit(client).status_code == 202
        assert submit(client).status_code == 202
        assert submit(client).status_code == 429
        # other users have their own quota
        assert submit(client, ALICE).status_code == 202
    finally:
        release.set()
    # let worker threads drain
    deadline = time.time() + 5
    while time.time() < deadline and any(
            j.status in ("queued", "running") for j in api._jobs.values()):
        time.sleep(0.02)
