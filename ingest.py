"""
ingest.py — Load, chunk, embed, and store policy documents in ChromaDB.
Run once to build the vector store. Re-run when documents update.
Smart re-indexing: skips unchanged files using MD5 hash comparison.
"""

import os

# Streamlit Cloud secrets support
# When running on Streamlit Cloud, push secrets into environment variables
# When running locally, load_dotenv() handles it — this block is safely skipped
try:
    import streamlit as st
    for key, value in st.secrets.items():
        os.environ[key] = str(value)
except:
    pass

from dotenv import load_dotenv
load_dotenv()

import hashlib
import json
from pathlib import Path
from datetime import datetime
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# ── Config from environment ───────────────────────────────────────────────────
CHROMA_PATH     = os.getenv("CHROMA_PATH",     "./loomis_vectordb")
DOCS_PATH       = os.getenv("DOCS_PATH",       "./policies")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
VERSION_STORE   = "./version_store.json"

CHUNK_SIZE    = 1000
CHUNK_OVERLAP = 150   # 15% overlap — prevents rules splitting across chunks


# ── Utility functions ─────────────────────────────────────────────────────────

def get_file_hash(filepath: str) -> str:
    """MD5 hash of file content — changes when file changes."""
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def load_version_store() -> dict:
    """Load record of what's currently indexed."""
    try:
        with open(VERSION_STORE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_version_store(store: dict):
    """Save updated index record to disk."""
    with open(VERSION_STORE, "w") as f:
        json.dump(store, f, indent=2)


def detect_category(filename: str) -> str:
    """Tag document with category based on filename."""
    name = filename.lower()
    if "vault" in name:
        return "vault_access"
    elif "hr" in name or "handbook" in name or "employee" in name:
        return "hr_policy"
    elif "route" in name or "safety" in name or "dispatch" in name:
        return "route_operations"
    else:
        return "general"


# ── Core pipeline steps ───────────────────────────────────────────────────────

def load_document(filepath: Path) -> Document:
    """Load a single .txt or .pdf file into a LangChain Document."""
    category = detect_category(filepath.name)

    if filepath.suffix == ".txt":
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

    elif filepath.suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader  = PdfReader(str(filepath))
            content = ""
            for page_num, page in enumerate(reader.pages):
                content += f"\n[Page {page_num + 1}]\n"
                content += page.extract_text() or ""
        except ImportError:
            print("pypdf not installed. Run: pip install pypdf")
            return None
    else:
        return None

    return Document(
        page_content = content,
        metadata     = {
            "source":     filepath.name,
            "category":   category,
            "file_path":  str(filepath),
            "indexed_at": datetime.now().isoformat(),
        }
    )


def chunk_documents(documents: list) -> list:
    """
    Split documents into overlapping chunks.
    RecursiveCharacterTextSplitter tries paragraph → sentence → word breaks.
    Never cuts mid-sentence when possible.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size         = CHUNK_SIZE,
        chunk_overlap      = CHUNK_OVERLAP,
        separators         = ["\n\n", "\n", ". ", " ", ""],
        length_function    = len,
        is_separator_regex = False,
    )

    chunks = splitter.split_documents(documents)

    # Add chunk index to metadata for audit trail
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_idx"] = i

    print(f"Chunked into {len(chunks)} chunks")
    print(f"Chunk size: {CHUNK_SIZE} chars | Overlap: {CHUNK_OVERLAP} chars")
    return chunks


def build_vector_store(chunks: list) -> Chroma:
    """Embed chunks and store in ChromaDB."""
    print(f"\nLoading embedding model: {EMBEDDING_MODEL}")
    print("Runs on CPU — no GPU needed, no data leaves network")

    embeddings = HuggingFaceEmbeddings(
        model_name    = EMBEDDING_MODEL,
        model_kwargs  = {"device": "cpu"},
        encode_kwargs = {"normalize_embeddings": True}
    )

    print(f"Embedding {len(chunks)} chunks and storing in ChromaDB...")

    vectorstore = Chroma.from_documents(
        documents         = chunks,
        embedding         = embeddings,
        persist_directory = CHROMA_PATH,
        collection_name   = "loomis_policies"
    )

    count = vectorstore._collection.count()
    print(f"Vector store built at: {CHROMA_PATH}")
    print(f"Total chunks indexed:  {count}")

    return vectorstore


# ── Smart ingestion — only re-index changed files ─────────────────────────────

def smart_ingest():
    """
    Main ingestion function.
    Checks file hashes — only processes files that changed since last run.
    Prevents duplicate chunks in ChromaDB.
    """
    print("=" * 55)
    print("LOOMIS RAG — DOCUMENT INGESTION")
    print("=" * 55)

    docs_path     = Path(DOCS_PATH)
    version_store = load_version_store()
    changed_files = []
    skipped_files = []

    # Check which files need re-indexing
    for filepath in docs_path.glob("*"):
        if filepath.suffix not in [".txt", ".pdf"]:
            continue

        current_hash = get_file_hash(str(filepath))
        filename     = filepath.name

        if filename in version_store:
            if version_store[filename]["hash"] == current_hash:
                skipped_files.append(filename)
                continue

        changed_files.append(filepath)

    print(f"\nFiles to index:  {len(changed_files)}")
    print(f"Files unchanged: {len(skipped_files)} (skipped)")

    if not changed_files:
        print("\nAll documents up to date. Nothing to re-index.")
        return

    # Load changed files
    docs_to_index = []
    for filepath in changed_files:
        print(f"Loading: {filepath.name}")
        doc = load_document(filepath)
        if doc:
            docs_to_index.append(doc)
            print(f"  → {doc.metadata['category']} | {len(doc.page_content)} chars")

    if not docs_to_index:
        print("No valid documents found.")
        return

    # Chunk
    chunks = chunk_documents(docs_to_index)

    # Build vector store
    build_vector_store(chunks)

    # Update version store
    for filepath in changed_files:
        version_store[filepath.name] = {
            "hash":       get_file_hash(str(filepath)),
            "indexed_at": datetime.now().isoformat(),
        }

    save_version_store(version_store)

    print("\nVersion store updated.")
    print("Ingestion complete.")
    print("=" * 55)


if __name__ == "__main__":
    smart_ingest()
