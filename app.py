"""
app.py — Streamlit UI for Loomis Policy Assistant.
Run locally:  streamlit run app.py
Deployed on:  Streamlit Cloud (share.streamlit.io)

Features:
- Chat tab: conversational Q&A with streaming responses
- Audit Log tab: every query logged with source, safety, metadata
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


# ── Main tabs ─────────────────────────────────────────────────────────────────

chat_tab, audit_tab = st.tabs(["💬 Chat", "📋 Audit Log"])


# ══════════════════════════════════════════════════════════════════════════════
# CHAT TAB
# ══════════════════════════════════════════════════════════════════════════════

with chat_tab:

    # Chat history display
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

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

    # Get question from chat input or demo button
    question = st.chat_input("Ask a policy question...")

    if st.session_state.pending_question:
        question = st.session_state.pending_question
        st.session_state.pending_question = None

    if question:
        st.session_state.messages.append({
            "role":    "user",
            "content": question
        })

        with st.chat_message("user"):
            st.write(question)

        category_filter = None if category == "All documents" else category

        with st.chat_message("assistant"):

            if use_streaming:
                response_placeholder = st.empty()
                full_response        = ""

                for chunk in stream_rag(question, category_filter):
                    full_response += chunk
                    response_placeholder.write(full_response + "▌")

                response_placeholder.write(full_response)

                result = run_rag(question, category_filter)

                if not result["is_safe"]:
                    response_placeholder.write(result["answer"])
                    full_response = result["answer"]

            else:
                with st.spinner("Searching policy documents..."):
                    result = run_rag(question, category_filter)

                st.write(result["answer"])
                full_response = result["answer"]

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

            st.session_state.messages.append({
                "role":     "assistant",
                "content":  full_response,
                "metadata": result
            })

        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# AUDIT LOG TAB
# ══════════════════════════════════════════════════════════════════════════════

with audit_tab:

    st.subheader("Session Audit Log")
    st.caption(
        "Every query logged with source document, chunks retrieved, "
        "safety gate result, and quote verification. "
        "In production this writes to an immutable PostgreSQL database "
        "retained for 7 years per SOX compliance requirements."
    )

    # Build query/response pairs from message history
    queries  = []
    messages = st.session_state.messages

    for i, msg in enumerate(messages):
        if msg["role"] == "user":
            if i + 1 < len(messages):
                response = messages[i + 1]
                if response["role"] == "assistant":
                    meta = response.get("metadata", {})
                    queries.append({
                        "index":          len(queries) + 1,
                        "question":       msg["content"],
                        "answer":         response["content"],
                        "sources":        meta.get("sources",        []),
                        "chunks_found":   meta.get("chunks_found",   0),
                        "safety_passed":  meta.get("is_safe",        True),
                        "quote_verified": meta.get("quote_verified", True),
                        "model":          meta.get("model",          "unknown"),
                    })

    if not queries:
        st.info(
            "No queries yet. Go to the **💬 Chat** tab and ask a question — "
            "every interaction will appear here automatically."
        )

    else:
        # Summary metrics
        total    = len(queries)
        safe     = sum(1 for q in queries if q["safety_passed"])
        blocked  = total - safe
        verified = sum(1 for q in queries if q["quote_verified"])

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total queries",   total)
        col2.metric("Safety passed",   safe)
        col3.metric("Safety blocked",  blocked)
        col4.metric("Quotes verified", verified)

        st.divider()

        # Most recent first
        for record in reversed(queries):
            safety_icon = "✅" if record["safety_passed"]  else "⚠️"
            quote_icon  = "✅" if record["quote_verified"] else "⚠️"

            question_preview = (
                record["question"][:55] + "..."
                if len(record["question"]) > 55
                else record["question"]
            )

            label = f"{safety_icon} Query {record['index']}: {question_preview}"

            # Expand most recent automatically
            is_latest = record["index"] == len(queries)

            with st.expander(label, expanded=is_latest):

                c1, c2, c3 = st.columns(3)
                c1.metric(
                    "Safety Gate",
                    "✅ Passed" if record["safety_passed"] else "⚠️ BLOCKED"
                )
                c2.metric(
                    "Quote Verified",
                    f"{quote_icon} {'Yes' if record['quote_verified'] else 'No'}"
                )
                c3.metric("Chunks Retrieved", record["chunks_found"])

                st.write("**Question asked:**")
                st.info(record["question"])

                st.write("**Answer returned:**")
                if record["safety_passed"]:
                    st.success(
                        record["answer"][:400] +
                        ("..." if len(record["answer"]) > 400 else "")
                    )
                else:
                    st.warning(record["answer"])

                st.write("**Source documents retrieved:**")
                if record["sources"]:
                    for source in record["sources"]:
                        st.write(f"  • `{source}`")
                else:
                    st.write("  No sources — question was out of scope")

                st.write(f"**Model used:** `{record['model']}`")

                st.divider()
                st.caption(
                    "In production: employee ID, timestamp, token count, "
                    "section, page number, and document version are also logged "
                    "to an append-only database."
                )
