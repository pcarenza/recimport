"""Framework-free pipeline: shared link/text -> recipe data (reusable by Streamlit/FastAPI)."""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

import extractor
import rtk

_TRAIL = ".,)!?\"'"
_URL_RE = re.compile(r"https?://[^\s<>]+", re.I)
_SCHEMELESS_RE = re.compile(
    r"(?<![\w/.@-])((?:www\.|m\.)?(?:youtu\.be|youtube\.com|facebook\.com|fb\.watch|fb\.com|instagram\.com|instagr\.am)/[^\s<>]+)", re.I)
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_first_url(text: str) -> str | None:
    """Return the first video URL found in arbitrary shared text, or None."""
    if not text:
        return None
    text = text.strip()
    m = _URL_RE.search(text)
    if m:
        return m.group(0).rstrip(_TRAIL)
    m = _SCHEMELESS_RE.search(text)
    if m:
        return "https://" + m.group(1).rstrip(_TRAIL)
    if _ID_RE.match(text):
        return "https://www.youtube.com/watch?v=" + text
    return None


@dataclass
class PipelineResult:
    data: dict
    canonical_url: str
    thumbnail: bytes | None
    source: str  # 'youtube' | 'facebook' | 'instagram'
    title: str


def run_pipeline(url_or_text: str, *, api_key: str, model: str,
                 languages: Sequence[str] = ("en",), transcript: str | None = None,
                 webshare_username: str | None = None,
                 webshare_password: str | None = None) -> PipelineResult:
    url = extract_first_url(url_or_text)
    if url is None:
        raise ValueError("No video link found")
    have_proxy = bool(webshare_username and webshare_password)

    if rtk.is_social_video_url(url):
        proxies = (None, f"http://{webshare_username}-rotate:{webshare_password}@p.webshare.io:80") \
            if have_proxy else (None,)
        media, mime, info = rtk.fetch_social_media(url, proxies)
        data = extractor.extract_recipe_from_media(media, mime, api_key, model, info["description"])
        thumb = rtk.fetch_image_png(info["thumbnail"]) if info.get("thumbnail") else None
        source = "instagram" if rtk.is_instagram_url(url) else "facebook"
        canonical = url
    else:
        vid = rtk.extract_video_id(url)
        canonical = f"https://www.youtube.com/watch?v={vid}"
        if transcript and transcript.strip():
            text = transcript.strip()
        else:
            proxy_config = None
            if have_proxy:
                from youtube_transcript_api.proxies import WebshareProxyConfig
                proxy_config = WebshareProxyConfig(proxy_username=webshare_username,
                                                   proxy_password=webshare_password)
            text, _lang = rtk.fetch_transcript(vid, languages, proxy_config)
        data = extractor.extract_recipe(text, api_key, model)
        thumb = rtk.fetch_thumbnail_png(vid)
        source = "youtube"

    return PipelineResult(data=data, canonical_url=canonical, thumbnail=thumb,
                          source=source, title=data.get("title", ""))


def build_rtk_file(result: PipelineResult) -> tuple[str, bytes]:
    recipe, _rid = rtk.build_recipe(result.data, result.canonical_url, result.thumbnail)
    name = re.sub(r"[^\w\-]+", "_", result.title).strip("_")[:60] or "recipe"
    return f"{name}.rtk", rtk.build_rtk(recipe, result.thumbnail)
