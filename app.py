"""
app.py — Streamlit UI for Loomis Policy Assistant.
Run locally:  streamlit run app.py
Deployed on:  Streamlit Cloud (share.streamlit.io)
"""

import os

# Streamlit Cloud secrets support
# Must happen before any other imports that read env vars
try:
    import streamlit as st
    for key, value in st.secrets.items():
        os.environ[key] = str(value)
except:
    pass

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
from chain import run_rag, stream_rag
from pathlib import Path


# ── Auto-ingest if vector store doesn't exist ─────────────────────────────────
# On Streamlit Cloud the filesystem resets on each cold start.
# If the loomis_vectordb folder doesn't exist, run ingestion automatically.

if not Path(os.getenv("CHROMA_PATH", "./loomis_vectordb")).exists():
    with st.spinner("Building knowledge base from policy documents..."):
        from ingest import smart_ingest
        smart_ingest()


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title = "Loomis Policy Assistant",
    page_icon  = "🏦",
    layout     = "wide"
)


# ── Header ────────────────────────────────────────────────────────────────────

st.title("🏦 Loomis Armored US — Policy Assistant")
st.caption(
    "Ask questions about internal policies, procedures, and guidelines. "
    "Every answer is sourced directly from official Loomis documents."
)


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Settings")

    category = st.selectbox(
        "Filter by document category",
        options = [
            "All documents",
            "vault_access",
            "hr_policy",
            "route_operations"
        ],
        help = "Restrict search to a specific document type"
    )

    use_streaming = st.toggle(
        "Stream responses",
        value = True,
        help  = "Show answer as it generates token by token"
    )

    st.divider()

    # System info
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    base  = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    mode  = "On-Prem (Ollama)" if "11434" in base or "localhost" in base else "Cloud (OpenAI)"

    st.caption(f"**Mode:** {mode}")
    st.caption(f"**Model:** {model}")
    st.caption(f"**Embeddings:** all-MiniLM-L6-v2 (CPU)")
    st.caption(f"**Vector store:** ChromaDB (local)")

    st.divider()
    st.caption("🔒 All data stays on-prem in production")
    st.caption("📋 Every query logged for compliance")
    st.caption("✅ Safety gate on every response")

    st.divider()

    if st.button("🗑️ Clear conversation"):
        st.session_state.messages = []
        st.rerun()

    # Demo questions
    st.divider()
    st.subheader("Try these questions")

    demo_questions = [
        "How many people are required for vault access?",
        "How many vacation days do I get per year?",
        "Can I access the vault alone on weekends?",
        "What happens if visibility is low on a route?",
        "What is the CEO's home address?",
    ]

    for dq in demo_questions:
        if st.button(dq, use_container_width=True):
            st.session_state.pending_question = dq
            st.rerun()


# ── Session state ─────────────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_question" not in st.session_state:
    st.session_state.pending_question = None


# ── Chat history display ──────────────────────────────────────────────────────

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

        # Show source metadata for assistant messages
        if msg["role"] == "assistant" and "metadata" in msg:
            meta = msg["metadata"]
            with st.expander("📋 Source details", expanded=False):
                col1, col2, col3 = st.columns(3)
                col1.metric("Chunks found", meta.get("chunks_found", 0))
                col2.metric("Safety gate",  "✅ Passed" if meta.get("is_safe") else "⚠️ Blocked")
                col3.metric("Quote check",  "✅ Verified" if meta.get("quote_verified") else "⚠️ Check")

                if meta.get("sources"):
                    st.write("**Source documents:**")
                    for source in meta["sources"]:
                        st.write(f"  • {source}")

                st.write(f"**Model:** {meta.get('model', 'unknown')}")


# ── Handle input ──────────────────────────────────────────────────────────────

# Get question from chat input or demo button
question = st.chat_input("Ask a policy question...")

# Check for pending question from sidebar button
if st.session_state.pending_question:
    question = st.session_state.pending_question
    st.session_state.pending_question = None

if question:
    # Add user message to history
    st.session_state.messages.append({
        "role":    "user",
        "content": question
    })

    with st.chat_message("user"):
        st.write(question)

    # Determine category filter
    category_filter = None if category == "All documents" else category

    # Generate answer
    with st.chat_message("assistant"):

        if use_streaming:
            # Stream tokens in real time — typewriter effect
            response_placeholder = st.empty()
            full_response        = ""

            for chunk in stream_rag(question, category_filter):
                full_response += chunk
                response_placeholder.write(full_response + "▌")

            response_placeholder.write(full_response)

            # Run full pipeline separately to get metadata and safety check
            result = run_rag(question, category_filter)

            # If safety gate failed — override the streamed answer
            if not result["is_safe"]:
                response_placeholder.write(result["answer"])
                full_response = result["answer"]

        else:
            # Non-streaming — wait for full response
            with st.spinner("Searching policy documents..."):
                result = run_rag(question, category_filter)

            st.write(result["answer"])
            full_response = result["answer"]
            result        = result

        # Show source details
        with st.expander("📋 Source details", expanded=False):
            col1, col2, col3 = st.columns(3)
            col1.metric("Chunks found", result["chunks_found"])
            col2.metric("Safety gate",  "✅ Passed" if result["is_safe"] else "⚠️ Blocked")
            col3.metric("Quote check",  "✅ Verified" if result["quote_verified"] else "⚠️ Check")

            if result["sources"]:
                st.write("**Source documents:**")
                for source in result["sources"]:
                    st.write(f"  • {source}")

            st.write(f"**Model:** {result['model']}")

        # Save to conversation history
        st.session_state.messages.append({
            "role":     "assistant",
            "content":  full_response,
            "metadata": result
        })
