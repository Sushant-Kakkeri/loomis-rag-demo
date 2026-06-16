"""
app.py — Streamlit UI for Loomis Policy Assistant.
Run with: streamlit run app.py
"""

import streamlit as st
from chain import run_rag, stream_rag

# Page config
st.set_page_config(
    page_title = "Loomis Policy Assistant",
    page_icon  = "🏦",
    layout     = "wide"
)

# Header
st.title("🏦 Loomis Armored — Policy Assistant")
st.caption("Ask questions about internal policies, procedures, and guidelines.")

# Sidebar — controls
with st.sidebar:
    st.header("Settings")

    category = st.selectbox(
        "Filter by document category",
        options = [
            "All documents",
            "vault_access",
            "hr_policy",
            "route_operations"
        ]
    )

    use_streaming = st.toggle("Stream responses", value=True)

    st.divider()
    st.caption("🔒 All data stays on-prem")
    st.caption("📋 Every query is logged for compliance")
    st.caption("⚡ Powered by Llama 3.1 + ChromaDB")

    st.divider()

    if st.button("Clear conversation"):
        st.session_state.messages = []
        st.rerun()

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

        # Show metadata for assistant messages
        if msg["role"] == "assistant" and "metadata" in msg:
            meta = msg["metadata"]
            with st.expander("📋 Source details", expanded=False):
                col1, col2, col3 = st.columns(3)
                col1.metric("Chunks found", meta.get("chunks_found", 0))
                col2.metric("Safe", "✅" if meta.get("is_safe") else "⚠️")
                col3.metric("Quote verified", "✅" if meta.get("quote_verified") else "⚠️")

                if meta.get("sources"):
                    st.write("**Sources:**")
                    for source in meta["sources"]:
                        st.write(f"  • {source}")

# Chat input
if question := st.chat_input("Ask a policy question..."):

    # Add user message
    st.session_state.messages.append({
        "role":    "user",
        "content": question
    })

    with st.chat_message("user"):
        st.write(question)

    # Get answer
    category_filter = None if category == "All documents" else category

    with st.chat_message("assistant"):
        if use_streaming:
            # Stream tokens in real time
            response_placeholder = st.empty()
            full_response = ""

            for chunk in stream_rag(question, category_filter):
                full_response += chunk
                response_placeholder.write(full_response + "▌")

            response_placeholder.write(full_response)

            # Run full pipeline for metadata
            result = run_rag(question, category_filter)

        else:
            with st.spinner("Searching policies..."):
                result = run_rag(question, category_filter)

            st.write(result["answer"])

        # Show source details
        with st.expander("📋 Source details", expanded=False):
            col1, col2, col3 = st.columns(3)
            col1.metric("Chunks found", result["chunks_found"])
            col2.metric("Safe",         "✅" if result["is_safe"] else "⚠️")
            col3.metric("Verified",     "✅" if result["quote_verified"] else "⚠️")

            if result["sources"]:
                st.write("**Sources:**")
                for source in result["sources"]:
                    st.write(f"  • {source}")

        # Save to history
        st.session_state.messages.append({
            "role":     "assistant",
            "content":  result["answer"],
            "metadata": result
        })