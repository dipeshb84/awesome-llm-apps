import streamlit as st
import tempfile
import requests
import re
import os
from embedchain import App
from youtube_transcript_api import YouTubeTranscriptApi

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

# Initialize session state
if "rag" not in st.session_state:
    st.session_state.rag = None
if "loaded" not in st.session_state:
    st.session_state.loaded = False
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "video_title" not in st.session_state:
    st.session_state.video_title = ""
if "api_key" not in st.session_state:
    st.session_state.api_key = os.getenv("OPENAI_API_KEY", "")
if "video_url" not in st.session_state:
    st.session_state.video_url = ""

# Sidebar for configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    api_key = st.text_input(
        "OpenAI API Key",
        value=st.session_state.api_key,
        type="password",
        help="Enter your OpenAI API key. You can also set it as OPENAI_API_KEY environment variable."
    )
    
    video_url = st.text_input(
        "YouTube Video URL",
        value=st.session_state.video_url,
        placeholder="https://www.youtube.com/watch?v=...",
        help="Enter the YouTube video URL you want to chat with."
    )
    
    if st.button("Load Video"):
        if not api_key:
            st.error("⚠️ Please enter your OpenAI API key")
        elif not video_url:
            st.error("⚠️ Please enter a YouTube video URL")
        else:
            st.session_state.api_key = api_key
            st.session_state.video_url = video_url
            st.session_state.loaded = False
            st.session_state.rag = None
            st.session_state.chat_history = []
            st.session_state.video_title = ""
            st.rerun()


# ---------------------------------------
# AUTO LOAD VIDEO ON START
# ---------------------------------------

if not st.session_state.api_key or not st.session_state.video_url:
    st.info("👈 Please configure your API key and video URL in the sidebar to get started.")
    st.stop()

if not st.session_state.loaded:
    with st.spinner("Fetching transcript..."):
        transcript = fetch_transcript(st.session_state.video_url)

    if transcript:
        video_id = extract_video_id(st.session_state.video_url)
        title = fetch_title(video_id)

        db_path = tempfile.mkdtemp()
        st.session_state.rag = create_rag_app(st.session_state.api_key, db_path)

        with st.spinner("Indexing transcript..."):
            st.session_state.rag.add(transcript, data_type="text")

        st.session_state.loaded = True
        st.session_state.video_title = title

        st.success(f"✅ Loaded: {title}")
        st.info(f"📊 Transcript length: {len(transcript.split())} words")
    else:
        st.error("❌ No transcript available for this video.")
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
