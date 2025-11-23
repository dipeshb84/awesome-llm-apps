import streamlit as st
import tempfile
import requests
from embedchain import App
from youtube_transcript_api import YouTubeTranscriptApi
import re
import requests
# ---------------------------------------
# HARD-CODED VALUES (EDIT THESE)
# ---------------------------------------

API_KEY = "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"   # <-- put your key here
VIDEO_URL = "https://www.youtube.com/watch?v=HCeyLJP60LQ"  # <-- put video URL here

# ---------------------------------------
# Helper Functions
# ---------------------------------------

def create_rag_app(api_key, db_path):
    return App.from_config(
        config={
            "llm": {
                "provider": "openai",
                "config": {"model": "gpt-4o-mini", "temperature": 0.3, "api_key": api_key},
            },
            "vectordb": {
                "provider": "chroma",
                "config": {"dir": db_path},
            },
            "embedder": {
                "provider": "openai",
                "config": {"api_key": api_key},
            },
        }
    )

def extract_video_id(url: str) -> str:
    if "watch?v=" in url:
        return url.split("watch?v=")[1].split("&")[0]
    if "youtube.com/shorts/" in url:
        return url.split("shorts/")[1].split("?")[0]
    raise ValueError("Invalid YouTube URL")

def fetch_title(video_id):
    try:
        data = requests.get(
            f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        ).json()
        return data.get("title", "Unknown Title")
    except:
        return "Unknown Title"

def fetch_transcript(url: str) -> str:
    print(">>> FALLBACK TRANSCRIPT FETCH STARTED")

    video_id = extract_video_id(url)
    print(">>> Video ID:", video_id)

    # Try YouTubeTranscriptApi first
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Try auto-generated EN first
        try:
            transcript = transcript_list.find_generated_transcript(["en"])
            snippets = transcript.fetch()
            return " ".join([x["text"] for x in snippets])
        except:
            pass

    except Exception as e:
        print(">>> Transcript API failed, switching to timedtext fallback:", e)

    print(">>> Using timedtext fallback...")

    # Timedtext direct URL
    timedtext_url = (
        f"https://www.youtube.com/api/timedtext?"
        f"v={video_id}&lang=en&fmt=vtt"
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        resp = requests.get(timedtext_url, headers=headers, timeout=10)

        if resp.status_code != 200:
            print(">>> Timedtext returned status:", resp.status_code)
            return None

        vtt = resp.text

        # Remove timestamps and formatting
        cleaned = re.sub(r"\d{2}:\d{2}:\d{2}\.\d{3}.*", "", vtt)
        cleaned = cleaned.replace("WEBVTT", "").strip()

        if len(cleaned) < 10:
            print(">>> Timedtext returned too little content")
            return None

        print(">>> Fallback transcript fetched successfully")
        return cleaned

    except Exception as e:
        print(">>> Timedtext fetch failed:", e)
        return None



# ---------------------------------------
# Streamlit UI
# ---------------------------------------

st.title("📺 Chat with a YouTube Video (RAG + GPT-4o-mini)")
st.caption("API key and YouTube link are hard-coded for testing.")

# Initialize session state
if "rag" not in st.session_state:
    st.session_state.rag = None
if "loaded" not in st.session_state:
    st.session_state.loaded = False
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "video_title" not in st.session_state:
    st.session_state.video_title = ""


# ---------------------------------------
# AUTO LOAD VIDEO ON START
# ---------------------------------------

if not st.session_state.loaded:
    with st.spinner("Fetching transcript..."):
        transcript = fetch_transcript(VIDEO_URL)

    if transcript:
        video_id = extract_video_id(VIDEO_URL)
        title = fetch_title(video_id)

        db_path = tempfile.mkdtemp()
        st.session_state.rag = create_rag_app(API_KEY, db_path)

        with st.spinner("Indexing transcript..."):
            st.session_state.rag.add(transcript, data_type="text")

        st.session_state.loaded = True
        st.session_state.video_title = title

        st.success(f"✅ Loaded: {title}")
        st.info(f"📊 Transcript length: {len(transcript.split())} words")
    else:
        st.error("❌ No transcript available for this hard-coded video.")
        st.stop()


# ---------------------------------------
# Chat Section
# ---------------------------------------

st.subheader(f"🎬 {st.session_state.video_title}")

question = st.text_input("Ask a question about the video")

if question:
    with st.spinner("Thinking..."):
        answer = st.session_state.rag.chat(question)

    st.session_state.chat_history.append((question, answer))

    st.markdown("### 🧠 Answer")
    st.write(answer)

if st.session_state.chat_history:
    with st.expander("💬 Chat History"):
        for q, a in st.session_state.chat_history:
            st.markdown(f"**❓ {q}**")
            st.markdown(f"✅ {a}")
            st.markdown("---")
