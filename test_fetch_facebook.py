import pytest
import yt_dlp

import rtk


def make_fake(ok_formats, info_extra=None, raise_for=None, calls=None):
    class Fake:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True):
            if calls is not None:
                calls.append((self.opts["format"], self.opts.get("proxy")))
            if raise_for and self.opts.get("proxy") in raise_for:
                raise RuntimeError("proxy down")
            if self.opts["format"] in ok_formats:
                with open(self.opts["outtmpl"] % {"ext": "mp4"}, "wb") as f:
                    f.write(b"video")
            d = {"title": "T", "description": "D", "thumbnail": "th"}
            d.update(info_extra or {})
            return d

    return Fake


def test_first_selector(monkeypatch):
    calls = []
    monkeypatch.setattr(yt_dlp, "YoutubeDL", make_fake(set(rtk.FB_FORMATS), calls=calls))
    data, mime, info = rtk.fetch_facebook_media("u")
    assert data == b"video" and mime == "video/mp4"
    assert info == {"description": "D", "thumbnail": "th", "title": "T"}
    assert [c[0] for c in calls] == [rtk.FB_FORMATS[0]]


def test_falls_through_to_third(monkeypatch):
    calls = []
    monkeypatch.setattr(yt_dlp, "YoutubeDL", make_fake({rtk.FB_FORMATS[2]}, calls=calls))
    data, _, _ = rtk.fetch_facebook_media("u")
    assert data == b"video"
    assert [c[0] for c in calls] == list(rtk.FB_FORMATS)


def test_all_empty_too_large(monkeypatch):
    monkeypatch.setattr(yt_dlp, "YoutubeDL", make_fake(set(), {"filesize_approx": 40 * 1024 * 1024}))
    with pytest.raises(RuntimeError, match="too large"):
        rtk.fetch_facebook_media("u")


def test_all_empty_unknown_size(monkeypatch):
    monkeypatch.setattr(yt_dlp, "YoutubeDL", make_fake(set()))
    with pytest.raises(RuntimeError, match="No downloadable video file"):
        rtk.fetch_facebook_media("u")


def test_proxy_fallback(monkeypatch):
    monkeypatch.setattr(yt_dlp, "YoutubeDL", make_fake(set(rtk.FB_FORMATS), raise_for={"p1"}))
    data, _, _ = rtk.fetch_facebook_media("u", proxy_urls=("p1", "p2"))
    assert data == b"video"
