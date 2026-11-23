import io
import json
import zipfile

import pytest

import pipeline
from pipeline import PipelineResult, build_rtk_file, extract_first_url, run_pipeline

VID = "dQw4w9WgXcQ"
DATA = {"title": "Tasty Pie!", "ingredients": ["1 egg", "2 cups flour"], "instructions": ["Mix", "Bake"]}


@pytest.mark.parametrize("text,expected", [
    ("Check this out 🍳 https://fb.watch/abc/ so good", "https://fb.watch/abc/"),
    ("https://www.facebook.com/reel/123", "https://www.facebook.com/reel/123"),
    ("see (https://www.youtube.com/watch?v=dQw4w9WgXcQ).", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ('wow "https://fb.watch/x/"!?', "https://fb.watch/x/"),
    ("watch youtu.be/dQw4w9WgXcQ now", "https://youtu.be/dQw4w9WgXcQ"),
    ("youtube.com/watch?v=dQw4w9WgXcQ", "https://youtube.com/watch?v=dQw4w9WgXcQ"),
    (VID, f"https://www.youtube.com/watch?v={VID}"),
    ("Try this! https://www.instagram.com/reel/XXXX/?igsh=abc", "https://www.instagram.com/reel/XXXX/?igsh=abc"),
    ("so good https://www.instagram.com/reel/XXXX/?igsh=abc.", "https://www.instagram.com/reel/XXXX/?igsh=abc"),
    ("instagram.com/reel/abc/", "https://instagram.com/reel/abc/"),
    ("see instagr.am/p/abc/!", "https://instagr.am/p/abc/"),
    ("no link here", None),
    ("", None),
])
def test_extract_first_url(text, expected):
    assert extract_first_url(text) == expected


def test_no_link_raises():
    with pytest.raises(ValueError, match="No video link found"):
        run_pipeline("hello there", api_key="k", model="m")


def test_youtube_manual_transcript_skips_fetch(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("fetch_transcript must not be called")
    seen = {}
    monkeypatch.setattr(pipeline.rtk, "fetch_transcript", boom)
    monkeypatch.setattr(pipeline.extractor, "extract_recipe",
                        lambda t, k, m: seen.update(t=t, k=k, m=m) or dict(DATA))
    monkeypatch.setattr(pipeline.rtk, "fetch_thumbnail_png", lambda v: b"png")
    r = run_pipeline(f"https://youtu.be/{VID}", api_key="K", model="M", transcript="  my text ")
    assert seen == {"t": "my text", "k": "K", "m": "M"}
    assert r.source == "youtube" and r.thumbnail == b"png" and r.title == "Tasty Pie!"
    assert r.canonical_url == f"https://www.youtube.com/watch?v={VID}"


def test_youtube_fetch_passes_languages_and_proxy(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline.rtk, "fetch_transcript",
                        lambda vid, langs, pc: calls.append((vid, langs, pc)) or ("tx", "fr"))
    monkeypatch.setattr(pipeline.extractor, "extract_recipe", lambda t, k, m: dict(DATA))
    monkeypatch.setattr(pipeline.rtk, "fetch_thumbnail_png", lambda v: None)
    run_pipeline(VID, api_key="K", model="M", languages=("fr", "en"))
    assert calls[-1] == (VID, ("fr", "en"), None)
    pytest.importorskip("youtube_transcript_api")
    run_pipeline(VID, api_key="K", model="M", webshare_username="u", webshare_password="p")
    pc = calls[-1][2]
    assert pc is not None and pc.proxy_username == "u" and pc.proxy_password == "p"


@pytest.mark.parametrize("creds,expected", [
    ({}, (None,)),
    ({"webshare_username": "u"}, (None,)),
    ({"webshare_username": "u", "webshare_password": "p"}, (None, "http://u-rotate:p@p.webshare.io:80")),
])
def test_facebook_path(monkeypatch, creds, expected):
    seen = {}
    monkeypatch.setattr(pipeline.rtk, "fetch_social_media",
                        lambda url, proxies: seen.update(url=url, proxies=proxies)
                        or (b"vid", "video/mp4", {"description": "CAPTION", "thumbnail": "http://t/i.jpg"}))
    monkeypatch.setattr(pipeline.extractor, "extract_recipe_from_media",
                        lambda media, mime, k, m, cap: seen.update(media=media, mime=mime, cap=cap) or dict(DATA))
    monkeypatch.setattr(pipeline.rtk, "fetch_image_png", lambda u: b"thumb")
    r = run_pipeline("look https://fb.watch/abc/ yum", api_key="K", model="M", **creds)
    assert seen["proxies"] == expected
    assert seen["url"] == "https://fb.watch/abc/"
    assert seen["cap"] == "CAPTION" and seen["media"] == b"vid" and seen["mime"] == "video/mp4"
    assert r.source == "facebook" and r.thumbnail == b"thumb" and r.canonical_url == "https://fb.watch/abc/"


def test_instagram_path(monkeypatch):
    seen = {}
    monkeypatch.setattr(pipeline.rtk, "fetch_social_media",
                        lambda url, proxies: seen.update(url=url, proxies=proxies)
                        or (b"vid", "video/mp4", {"description": "CAPTION", "thumbnail": ""}))
    monkeypatch.setattr(pipeline.extractor, "extract_recipe_from_media",
                        lambda media, mime, k, m, cap: seen.update(cap=cap) or dict(DATA))
    url = "https://www.instagram.com/reel/XXXX/?igsh=abc"
    r = run_pipeline(f"yum {url}", api_key="K", model="M", webshare_username="u", webshare_password="p")
    assert seen["url"] == url and seen["cap"] == "CAPTION"
    assert seen["proxies"] == (None, "http://u-rotate:p@p.webshare.io:80")
    assert r.source == "instagram" and r.canonical_url == url and r.thumbnail is None


def test_build_rtk_file():
    res = PipelineResult(data=dict(DATA), canonical_url="https://x/y", thumbnail=None,
                         source="youtube", title=DATA["title"])
    name, blob = build_rtk_file(res)
    assert name == "Tasty_Pie.rtk"
    z = zipfile.ZipFile(io.BytesIO(blob))
    recipe = json.loads(z.read("recipes_0.json"))[0]
    assert recipe["ingredients"] == "1 egg\n2 cups flour"
    assert recipe["url"] == "https://x/y"


def test_build_rtk_file_default_name():
    res = PipelineResult(data={"title": "!!!"}, canonical_url="u", thumbnail=None, source="youtube", title="!!!")
    assert build_rtk_file(res)[0] == "recipe.rtk"
