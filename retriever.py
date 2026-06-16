"""
retriever.py — ChromaDB retrieval with metadata filtering.
"""

import os
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

load_dotenv()

CHROMA_PATH     = os.getenv("CHROMA_PATH",    "./loomis_vectordb")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")


def get_retriever(
    category_filter: str = None,
    top_k:           int = 5,
    score_threshold: float = 0.3
):
    """
    Returns a LangChain retriever backed by ChromaDB.

    category_filter: limit search to specific document category
                     "vault_access" | "hr_policy" | "route_operations"
    top_k:           number of chunks to return
    score_threshold: minimum similarity score (0-1)
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
    search_kwargs = {
        "k": top_k,
    }

    # Add category filter if specified
    if category_filter:
        search_kwargs["filter"] = {"category": category_filter}

    retriever = vectorstore.as_retriever(
        search_type   = "similarity",
        search_kwargs = search_kwargs
    )

    return retriever


def format_docs(docs) -> str:
    """Format retrieved chunks into context block for the prompt."""
    if not docs:
        return "No relevant policy information found."

    formatted = []
    for doc in docs:
        source   = doc.metadata.get("source",   "unknown")
        category = doc.metadata.get("category", "unknown")
        chunk    = doc.metadata.get("chunk_idx", 0)

        formatted.append(
            f"[Source: {source} | Category: {category} | Chunk: {chunk}]\n"
            f"{doc.page_content}"
        )

    return "\n\n---\n\n".join(formatted)


def test_retrieval(query: str, category: str = None):
    """Quick test — run a query and see what comes back."""
    retriever = get_retriever(category_filter=category)
    docs      = retriever.invoke(query)

    print(f"\nQuery: '{query}'")
    print(f"Category filter: {category or 'none'}")
    print(f"Chunks returned: {len(docs)}")
    print()

    for i, doc in enumerate(docs):
        print(f"Chunk {i+1}:")
        print(f"  Source:   {doc.metadata.get('source')}")
        print(f"  Category: {doc.metadata.get('category')}")
        print(f"  Preview:  {doc.page_content[:100]}...")
        print()


if __name__ == "__main__":
    # Test your retrieval before building the chain
    test_retrieval("How many people needed for vault access?")
    test_retrieval("How many vacation days do I get?")
    test_retrieval("What happens in bad weather on a route?")