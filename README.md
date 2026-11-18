# YouTube → RecetteTek (.rtk)

Streamlit app: YouTube link → transcript (`youtube-transcript-api`) → structured recipe (Gemini, schema-constrained JSON) → in-memory `.rtk` zip with a one-click download for My Recipe Box / RecetteTek.

Files: `app.py` (UI), `extractor.py` (LLM), `rtk.py` (transcript, thumbnail, packaging), `test_rtk.py`.

## Run locally
```bash
pip install -r requirements.txt
mkdir -p .streamlit && cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then edit the key
streamlit run app.py
```

## Deploy on Streamlit Community Cloud (free)
1. Get an API key at https://aistudio.google.com/apikey (free tier available).
2. Push this repo to GitHub (`git push -u origin main`; `secrets.toml` is git-ignored).
3. Go to https://share.streamlit.io, sign in with GitHub, click **Create app** → *Deploy a public app from GitHub*.
4. Pick the repo, branch, and main file `app.py`.
5. Open **Advanced settings → Secrets** and paste:
   ```toml
   GEMINI_API_KEY = "AIza..."
   ```
   (Later: app menu ⋮ → Settings → Secrets.)
6. Click **Deploy**. Anyone with the URL can spend your API credits — the free tier is rate-limited; on a paid key set a budget alert in Google Cloud, or make the app private (Share → restrict viewers).

## Facebook reels
Paste a **public** Facebook reel/video link. The app downloads it with `yt-dlp` (direct first, then through the Webshare proxy if configured) and sends the video to Gemini, which uses the speech, on-screen text and post caption. Limits: public videos only, ~19 MB max, and Facebook may block cloud IPs or change its site (update `yt-dlp` if downloads start failing).

## Backend API (Render / Android client)
`api.py` is a FastAPI service for the Android app. The Streamlit app is unchanged and keeps working.

Render settings: Build `pip install -r requirements.txt`, Start `uvicorn api:app --host 0.0.0.0 --port $PORT`.

Environment variables on Render:

| Name | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | yes* | Default Gemini key (*a client may send its own in `X-Gemini-Key`) |
| `APP_TOKEN` | yes | Shared bearer token, 16+ chars; acts as user `owner` |
| `APP_TOKENS` | no | Per-user tokens, `alice:token1,bob:token2` (16+ chars each); jobs are private per user |
| `GEMINI_MODEL` | no | Model override |
| `WEBSHARE_PROXY_USERNAME` / `WEBSHARE_PROXY_PASSWORD` | no | Residential proxy |
| `PYTHON_VERSION` | no | e.g. `3.12.7` |

Endpoints (all but `/health` need `Authorization: Bearer <token>`):

- `GET /health` -> `{"ok": true}`. No auth; call it first to wake the free-tier instance.
- `POST /v1/jobs` body `{"text": "<link or any shared text containing one>", "languages": ["en"], "transcript": null}` -> `202 {id, status}`. Optional header `X-Gemini-Key`.
- `GET /v1/jobs/{id}` -> `{status: queued|running|done|error, error, title, source, recipe, download_path}`. Poll every 2 s.
- `GET /v1/jobs/{id}/rtk` -> the `.rtk` file (`application/octet-stream`, attachment). 409 until the job is done.

Jobs live in memory for 30 minutes and are lost on restart or when the instance sleeps.

Test locally: `pip install -r requirements-dev.txt && pytest -q`.

## Import into My Recipe Box
Download the `.rtk`, open it on your phone/computer with RecetteTek (Settings → Import / Export → Import), and pick the file.

## Known limitation: YouTube blocks cloud IPs
YouTube frequently rejects transcript requests from datacenter IPs (Streamlit Cloud, Render, HF). Options:
- Paste the transcript manually in the app (built-in fallback).
- Set `WEBSHARE_PROXY_USERNAME` / `WEBSHARE_PROXY_PASSWORD` secrets (Webshare "Residential" proxy, paid) — the app uses them automatically.
- Run it locally, where it works from a home IP.
