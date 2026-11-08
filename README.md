# YouTube → RecetteTek (.rtk)

Streamlit app: YouTube link → transcript (`youtube-transcript-api`) → structured recipe (Claude, forced tool-use JSON) → in-memory `.rtk` zip with a one-click download for My Recipe Box / RecetteTek.

Files: `app.py` (UI), `extractor.py` (LLM), `rtk.py` (transcript, thumbnail, packaging), `test_rtk.py`.

## Run locally
```bash
pip install -r requirements.txt
mkdir -p .streamlit && cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then edit the key
streamlit run app.py
```

## Deploy on Streamlit Community Cloud (free)
1. Get an API key at https://console.anthropic.com (Settings → API keys).
2. Push this repo to GitHub (`git push -u origin main`; `secrets.toml` is git-ignored).
3. Go to https://share.streamlit.io, sign in with GitHub, click **Create app** → *Deploy a public app from GitHub*.
4. Pick the repo, branch, and main file `app.py`.
5. Open **Advanced settings → Secrets** and paste:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
   (Later: app menu ⋮ → Settings → Secrets.)
6. Click **Deploy**. Anyone with the URL can spend your API credits — set a spend limit in the Anthropic console, or make the app private (Share → restrict viewers).

## Import into My Recipe Box
Download the `.rtk`, open it on your phone/computer with RecetteTek (Settings → Import / Export → Import), and pick the file.

## Known limitation: YouTube blocks cloud IPs
YouTube frequently rejects transcript requests from datacenter IPs (Streamlit Cloud, Render, HF). Options:
- Paste the transcript manually in the app (built-in fallback).
- Set `WEBSHARE_PROXY_USERNAME` / `WEBSHARE_PROXY_PASSWORD` secrets (Webshare "Residential" proxy, paid) — the app uses them automatically.
- Run it locally, where it works from a home IP.
