"""
retriever.py — ChromaDB semantic search.
Embeds queries with sentence-transformers and returns relevant policy chunks.
Run standalone to test retrieval quality before building the full chain.
"""

import os

# Streamlit Cloud secrets support
try:
    import streamlit as st
    for key, value in st.secrets.items():
        os.environ[key] = str(value)
except:
    pass

from dotenv import load_dotenv
load_dotenv()

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

# ── Config ────────────────────────────────────────────────────────────────────
CHROMA_PATH     = os.getenv("CHROMA_PATH",     "./loomis_vectordb")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")


# ── Retriever factory ─────────────────────────────────────────────────────────

def get_retriever(
    category_filter: str = None,
    top_k:           int = 5,
    score_threshold: float = 0.3
):
    """
    Returns a LangChain retriever backed by ChromaDB.

    Args:
        category_filter: Restrict search to one document category.
                         Options: "vault_access" | "hr_policy" | "route_operations"
        top_k:           Number of chunks to return (default 5)
        score_threshold: Minimum similarity score 0-1 (default 0.3)

    Returns:
        LangChain retriever object — call .invoke(query) to search
    """
    embeddings = HuggingFaceEmbeddings(
        model_name    = EMBEDDING_MODEL,
        model_kwargs  = {"device": "cpu"},
        encode_kwargs = {"normalize_embeddings": True}
    )

    vectorstore = Chroma(
        persist_directory  = CHROMA_PATH,
        embedding_function = embeddings,
        collection_name    = "loomis_policies"
    )

    # Build search kwargs
    search_kwargs = {"k": top_k}

    # Add metadata filter if category specified
    # This prevents HR chunks appearing in vault queries and vice versa
    if category_filter:
        search_kwargs["filter"] = {"category": category_filter}

    retriever = vectorstore.as_retriever(
        search_type   = "similarity",
        search_kwargs = search_kwargs
    )

    return retriever


def format_docs(docs) -> str:
    """
    Format retrieved chunks into a clean context block for the LLM prompt.
    Each chunk gets a source header for the audit trail.
    """
    if not docs:
        return "No relevant policy information found."

    formatted = []
    for doc in docs:
        source   = doc.metadata.get("source",    "unknown")
        category = doc.metadata.get("category",  "unknown")
        section  = doc.metadata.get("section",   "")
        page     = doc.metadata.get("page",      "")
        chunk    = doc.metadata.get("chunk_idx", 0)

        header = f"[Source: {source} | Category: {category}"
        if section:
            header += f" | Section: {section}"
        if page:
            header += f" | Page: {page}"
        header += f" | Chunk: {chunk}]"

        formatted.append(f"{header}\n{doc.page_content}")

    return "\n\n---\n\n".join(formatted)


# ── Diagnostic test ───────────────────────────────────────────────────────────

def test_retrieval(query: str, category: str = None):
    """
    Test retrieval for a query and print results.
    Run this directly to verify ChromaDB is returning the right chunks
    before building the full RAG chain.
    """
    retriever = get_retriever(category_filter=category)
    docs      = retriever.invoke(query)

    print(f"\nQuery: '{query}'")
    print(f"Category filter: {category or 'none'}")
    print(f"Chunks returned: {len(docs)}")

    for i, doc in enumerate(docs):
        print(f"\nChunk {i + 1}:")
        print(f"  Source:   {doc.metadata.get('source')}")
        print(f"  Category: {doc.metadata.get('category')}")
        print(f"  Preview:  {doc.page_content[:100]}...")


if __name__ == "__main__":
    # Run these to verify retrieval is working correctly
    test_retrieval("How many people needed for vault access?")
    test_retrieval("How many vacation days do I get?")
    test_retrieval("What happens in bad weather on a route?")
