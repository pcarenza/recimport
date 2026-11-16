import re

import streamlit as st

from extractor import DEFAULT_MODEL, extract_recipe, extract_recipe_from_media
from rtk import (build_recipe, build_rtk, extract_video_id, fetch_facebook_media, fetch_image_png,
                 fetch_thumbnail_png, fetch_transcript, is_facebook_url)

st.set_page_config(page_title="Video → RecetteTek", page_icon="🍳")
st.title("🍳 Video → My Recipe Box")
st.caption("Paste a YouTube video or public Facebook reel link, get a `.rtk` file you can import into RecetteTek.")


def secret(name, default=None):
    try:
        return st.secrets[name]
    except Exception:
        import os
        return os.environ.get(name, default)


default_key = secret("GEMINI_API_KEY")
model = secret("GEMINI_MODEL", DEFAULT_MODEL)
from streamlit_local_storage import LocalStorage

STORE_KEY = "gemini_api_key"
store = LocalStorage()  # browser localStorage: lives on this device only
saved_key = store.getItem(STORE_KEY) or ""
with st.sidebar:
    st.header("Gemini API key")
    custom_key = st.text_input(
        "Use my own key (optional)", type="password", placeholder="AIza...", value=saved_key,
        help="Overrides the app's default free key, e.g. with a paid key.",
    ).strip()
    remember = st.checkbox(
        "Remember on this device", value=bool(saved_key),
        help="Stores the key in this browser's localStorage so you don't have to re-enter it. "
             "Don't use on shared or public computers.",
    )
if remember and custom_key and custom_key != saved_key:
    store.setItem(STORE_KEY, custom_key)
elif not remember and saved_key:
    store.eraseItem(STORE_KEY)
    store.storedItems.pop(STORE_KEY, None)
api_key = custom_key or default_key
if custom_key:
    st.sidebar.success("Using your key.")
elif default_key:
    st.sidebar.info("Using the app's default key.")
if not api_key:
    st.error("No Gemini API key: enter one in the sidebar or set GEMINI_API_KEY in the app's secrets.")
    st.stop()


def proxy_config():
    """Optional Webshare residential proxy; YouTube often blocks cloud IPs."""
    u, p = secret("WEBSHARE_PROXY_USERNAME"), secret("WEBSHARE_PROXY_PASSWORD")
    if u and p:
        from youtube_transcript_api.proxies import WebshareProxyConfig
        return WebshareProxyConfig(proxy_username=u, proxy_password=p)
    return None


def proxy_urls():
    """Direct first, then the Webshare residential proxy if configured (Facebook downloads)."""
    u, p = secret("WEBSHARE_PROXY_USERNAME"), secret("WEBSHARE_PROXY_PASSWORD")
    return (None, f"http://{u}-rotate:{p}@p.webshare.io:80") if u and p else (None,)


url = st.text_input("Video link", placeholder="https://www.youtube.com/watch?v=...  or  https://www.facebook.com/reel/...")
is_fb = is_facebook_url(url) if url.strip() else False
if is_fb:
    st.caption("Facebook reel detected: the video is downloaded and Gemini watches and listens to it (public videos only).")
    langs, manual = "en", ""
else:
    langs = st.text_input("Preferred subtitle languages (comma separated)", "en")
    manual = st.text_area("Or paste a transcript manually (used if automatic fetching is blocked)", height=100)

if st.button("Extract recipe", type="primary", disabled=not url.strip()):
    try:
        if is_fb:
            canonical = url.strip()
            with st.spinner("Downloading reel…"):
                media, mime, info = fetch_facebook_media(canonical, proxy_urls())
            with st.spinner("Gemini is watching the video…"):
                data = extract_recipe_from_media(media, mime, api_key, model, info["description"])
            thumb = fetch_image_png(info["thumbnail"]) if info["thumbnail"] else None
            lang, size = "video", len(media)
        else:
            vid = extract_video_id(url)
            canonical = f"https://www.youtube.com/watch?v={vid}"
            if manual.strip():
                transcript, lang = manual.strip(), "manual"
            else:
                with st.spinner("Fetching transcript…"):
                    preferred = [l.strip() for l in langs.split(",") if l.strip()] or ["en"]
                    transcript, lang = fetch_transcript(vid, preferred, proxy_config())
            with st.spinner("Extracting recipe with Gemini…"):
                data = extract_recipe(transcript, api_key, model)
            thumb = fetch_thumbnail_png(vid)
            size = len(transcript)
        st.session_state["result"] = (data, canonical, thumb, lang, size)
    except Exception as e:
        st.session_state.pop("result", None)
        st.error(f"{type(e).__name__}: {e}")
        if not is_fb and ("block" in str(e).lower() or "IP" in str(e)):
            st.info("YouTube is blocking this server's IP. Paste the transcript manually above, "
                    "or configure the optional WEBSHARE_PROXY_* secrets (see README).")
        elif is_fb:
            st.info("Facebook download failed. Only public reels/videos work; Facebook may also block "
                    "this server's IP (the optional WEBSHARE_PROXY_* secrets are tried as a fallback).")

if "result" in st.session_state:
    data, canonical, thumb, lang, n = st.session_state["result"]
    st.success(f"Video downloaded ({n/1e6:.1f} MB)." if lang == "video" else f"Transcript fetched ({lang}, {n:,} characters).")
    if thumb:
        st.image(thumb, width=320)
    st.subheader(data.get("title", ""))
    st.write(data.get("description", ""))
    c1, c2, c3 = st.columns(3)
    c1.metric("Prep (min)", data.get("preparationTime") or "–")
    c2.metric("Cook (min)", data.get("cookingTime") or "–")
    c3.metric("Total (min)", data.get("totalTime") or "–")
    st.write(f"**Servings:** {data.get('quantity') or '–'}  \n**Category:** {data.get('category') or '–'}")
    st.write("**Cookware:** " + (", ".join(data.get("cookware", [])) or "–"))
    st.markdown("**Ingredients**\n" + "\n".join(f"- {i}" for i in data.get("ingredients", [])))
    st.markdown("**Instructions**\n" + "\n".join(f"{n}. {s}" for n, s in enumerate(data.get("instructions", []), 1)))

    recipe, _ = build_recipe(data, canonical, thumb)
    rtk_bytes = build_rtk(recipe, thumb)
    fname = re.sub(r"[^\w\-]+", "_", recipe["title"]).strip("_")[:60] or "recipe"
    st.download_button("⬇️ Download .rtk", rtk_bytes, file_name=f"{fname}.rtk",
                       mime="application/octet-stream", type="primary")
