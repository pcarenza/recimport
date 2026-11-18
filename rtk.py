"""Helpers: YouTube id parsing, transcript fetching, thumbnail, and .rtk packaging."""
from __future__ import annotations

import io
import json
import re
import uuid
import zipfile
from datetime import datetime
from urllib.parse import parse_qs, urlparse

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_video_id(url: str) -> str:
    """Return the 11-char video id from any common YouTube URL form."""
    url = url.strip()
    if _ID_RE.match(url):
        return url
    p = urlparse(url if "//" in url else "https://" + url)
    host = (p.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    candidate = None
    if host == "youtu.be":
        candidate = p.path.lstrip("/").split("/")[0]
    elif host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
        if p.path == "/watch":
            candidate = parse_qs(p.query).get("v", [None])[0]
        else:
            m = re.match(r"^/(?:shorts|embed|live|v)/([^/?]+)", p.path)
            candidate = m.group(1) if m else None
    if candidate and _ID_RE.match(candidate):
        return candidate
    raise ValueError("Could not find a YouTube video id in that link.")


_FB_HOSTS = ("facebook.com", "fb.watch", "fb.com")
MAX_MEDIA_BYTES = 19 * 1024 * 1024  # Gemini inline-data limit is ~20 MB


def is_facebook_url(url: str) -> bool:
    p = urlparse(url.strip() if "//" in url else "https://" + url.strip())
    host = (p.hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _FB_HOSTS)


# Progressively smaller selectors, tried in order until a file fits under the cap.
FB_FORMATS = (
    "best[ext=mp4][filesize<?18M]/best[filesize<?18M]",
    "best[ext=mp4][height<=480]/best[height<=480]",
    "worst[ext=mp4]/worst",
)


def _fb_known_size(info: dict) -> int | None:
    """Best-known size in bytes from yt-dlp info (top level, else smallest format)."""
    info = info or {}
    top = info.get("filesize") or info.get("filesize_approx")
    if top:
        return int(top)
    sizes = [f.get("filesize") or f.get("filesize_approx") for f in info.get("formats") or []]
    sizes = [int(x) for x in sizes if x]
    return min(sizes) if sizes else None


def fetch_facebook_media(url: str, proxy_urls=(None,)) -> tuple[bytes, str, dict]:
    """Download a public Facebook reel/video with yt-dlp.

    Tries each proxy in `proxy_urls` in order (None = direct). Returns
    (mp4 bytes, mime type, info dict with 'description' and 'thumbnail').
    """
    import tempfile
    from pathlib import Path

    import yt_dlp

    mb = 1024 * 1024
    last = None
    for proxy in proxy_urls:
        with tempfile.TemporaryDirectory() as tmp:
            info = {}
            try:
                files = []
                for fmt in FB_FORMATS:
                    opts = {
                        "format": fmt,  # one file with video+audio
                        "outtmpl": str(Path(tmp) / "media.%(ext)s"),
                        "noplaylist": True,
                        "quiet": True,
                        "no_warnings": True,
                        "max_filesize": MAX_MEDIA_BYTES,
                        "socket_timeout": 20,
                        "retries": 2,
                    }
                    if proxy:
                        opts["proxy"] = proxy
                    try:
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            got = ydl.extract_info(url, download=True)
                        if got:
                            info = got
                    except yt_dlp.utils.DownloadError as e:
                        if "format" in str(e).lower() and "not available" in str(e).lower():
                            continue
                        raise
                    files = [f for f in Path(tmp).iterdir() if f.is_file()]
                    if files:
                        break
                if not files:
                    size = _fb_known_size(info)
                    if size and size > MAX_MEDIA_BYTES:
                        raise RuntimeError(
                            f"This video is too large to process (about {size / mb:.0f} MB; "
                            f"limit {MAX_MEDIA_BYTES // mb} MB). Try a shorter reel.")
                    raise RuntimeError("No downloadable video file was found "
                                       "(the video may be private, removed or too large).")
                data = files[0].read_bytes()
                if len(data) > MAX_MEDIA_BYTES:
                    raise RuntimeError(
                        f"This video is too large to process (about {len(data) / mb:.0f} MB; "
                        f"limit {MAX_MEDIA_BYTES // mb} MB). Try a shorter reel.")
                mime = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
                        ".m4a": "audio/mp4", ".mp3": "audio/mp3"}.get(files[0].suffix.lower(), "video/mp4")
                return data, mime, {"description": info.get("description") or "",
                                    "thumbnail": info.get("thumbnail") or "",
                                    "title": info.get("title") or ""}
            except Exception as e:  # try next proxy
                last = e
    raise last


def fetch_image_png(url: str) -> bytes | None:
    """Download any image URL and return PNG bytes (None on failure)."""
    import requests
    from PIL import Image

    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        out = io.BytesIO()
        Image.open(io.BytesIO(r.content)).convert("RGB").save(out, "PNG")
        return out.getvalue()
    except Exception:
        return None


def fetch_transcript(video_id: str, languages=("en",), proxy_config=None) -> tuple[str, str]:
    """Fetch a transcript (manual or auto-generated). Returns (text, language_code).

    Tries the preferred languages first, then falls back to whatever transcript
    exists (translated to English if possible).
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi(proxy_config=proxy_config) if proxy_config else YouTubeTranscriptApi()
    tlist = api.list(video_id)
    try:
        tr = tlist.find_transcript(list(languages))
    except Exception:
        tr = next(iter(tlist))  # any available transcript
        if tr.is_translatable and tr.language_code not in languages:
            try:
                tr = tr.translate(languages[0])
            except Exception:
                pass
    fetched = tr.fetch()
    text = " ".join(s.text.replace("\n", " ") for s in fetched)
    return re.sub(r"\s+", " ", text).strip(), tr.language_code


def fetch_thumbnail_png(video_id: str) -> bytes | None:
    """Download the video thumbnail and return it as PNG bytes (None on failure)."""
    import requests
    from PIL import Image

    for name in ("maxresdefault", "hqdefault"):
        try:
            r = requests.get(f"https://img.youtube.com/vi/{video_id}/{name}.jpg", timeout=10)
            if r.status_code == 200 and len(r.content) > 2000:  # skip YouTube's tiny placeholder
                out = io.BytesIO()
                Image.open(io.BytesIO(r.content)).convert("RGB").save(out, "PNG")
                return out.getvalue()
        except Exception:
            continue
    return None


def _join(value) -> str:
    if isinstance(value, (list, tuple)):
        return "\n".join(str(v).strip() for v in value if str(v).strip())
    return str(value or "").strip()


def _digits(value) -> str:
    m = re.search(r"\d+", str(value or ""))
    return m.group(0) if m else ""


def build_recipe(data: dict, source_url: str = "", thumbnail: bytes | None = None) -> tuple[dict, str]:
    """Map LLM output to an RTK recipe object. Returns (recipe, uuid)."""
    rid = str(uuid.uuid4())
    prep, cook = _digits(data.get("preparationTime")), _digits(data.get("cookingTime"))
    total = data.get("totalTime")
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = int(prep or 0) + int(cook or 0)
    recipe = {
        "uuid": rid,
        "title": str(data.get("title") or "Untitled recipe").strip(),
        "description": str(data.get("description") or "").strip(),
        "preparationTime": prep,
        "cookingTime": cook,
        "totalTime": total,
        "quantity": str(data.get("quantity") or "").strip(),
        "cookware": _join(data.get("cookware")),
        "ingredients": _join(data.get("ingredients")),   # newline-separated string
        "instructions": _join(data.get("instructions")),  # newline-separated string
        "pictures": [f"{rid}.png"] if thumbnail else [],
        "url": source_url,
        "video": source_url,
        "notes": "",
        "favorite": False,
        "categories": [{"title": str(data["category"]).strip()}] if data.get("category") else [],
        "tags": [],
        "lastModifiedDate": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return recipe, rid


def build_rtk(recipe: dict, thumbnail: bytes | None = None) -> bytes:
    """Package a recipe into an in-memory .rtk (zip) archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("recipes_0.json", json.dumps([recipe], ensure_ascii=False, indent=2))
        for name in ("categories.json", "tags.json", "calendar.json"):
            z.writestr(name, "[]")
        if thumbnail:
            z.writestr(f"{recipe['uuid']}.png", thumbnail)
    return buf.getvalue()
