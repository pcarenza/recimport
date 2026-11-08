import re

import streamlit as st

from extractor import DEFAULT_MODEL, extract_recipe
from rtk import build_recipe, build_rtk, extract_video_id, fetch_thumbnail_png, fetch_transcript

st.set_page_config(page_title="YouTube → RecetteTek", page_icon="🍳")
st.title("🍳 YouTube → My Recipe Box")
st.caption("Paste a cooking video link, get a `.rtk` file you can import into RecetteTek.")


def secret(name, default=None):
    try:
        return st.secrets[name]
    except Exception:
        import os
        return os.environ.get(name, default)


api_key = secret("GEMINI_API_KEY")
model = secret("GEMINI_MODEL", DEFAULT_MODEL)
if not api_key:
    st.error("GEMINI_API_KEY is not configured (add it to the app's secrets).")
    st.stop()


def proxy_config():
    """Optional Webshare residential proxy; YouTube often blocks cloud IPs."""
    u, p = secret("WEBSHARE_PROXY_USERNAME"), secret("WEBSHARE_PROXY_PASSWORD")
    if u and p:
        from youtube_transcript_api.proxies import WebshareProxyConfig
        return WebshareProxyConfig(proxy_username=u, proxy_password=p)
    return None


url = st.text_input("YouTube link", placeholder="https://www.youtube.com/watch?v=...")
langs = st.text_input("Preferred subtitle languages (comma separated)", "en")
manual = st.text_area("Or paste a transcript manually (used if automatic fetching is blocked)", height=100)

if st.button("Extract recipe", type="primary", disabled=not url.strip()):
    try:
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
        with st.spinner("Packaging…"):
            thumb = fetch_thumbnail_png(vid)
        st.session_state["result"] = (data, canonical, thumb, lang, len(transcript))
    except Exception as e:
        st.session_state.pop("result", None)
        st.error(f"{type(e).__name__}: {e}")
        if "block" in str(e).lower() or "IP" in str(e):
            st.info("YouTube is blocking this server's IP. Paste the transcript manually above, "
                    "or configure the optional WEBSHARE_PROXY_* secrets (see README).")

if "result" in st.session_state:
    data, canonical, thumb, lang, n = st.session_state["result"]
    st.success(f"Transcript fetched ({lang}, {n:,} characters).")
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
                       mime="application/zip", type="primary")
