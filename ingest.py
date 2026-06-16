"""
ingest.py — Load, chunk, embed, and store policy documents.
Run once to build the vector store. Re-run when documents update.
"""

import os
import hashlib
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

load_dotenv()

CHROMA_PATH    = os.getenv("CHROMA_PATH", "./loomis_vectordb")
DOCS_PATH      = os.getenv("DOCS_PATH",   "./policies")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
VERSION_STORE  = "./version_store.json"

# Chunk size and overlap — tuned for policy documents
CHUNK_SIZE    = 1000
CHUNK_OVERLAP = 150   # 15% overlap


def get_file_hash(filepath: str) -> str:
    """MD5 hash — detects if file changed since last index."""
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def load_version_store() -> dict:
    try:
        with open(VERSION_STORE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_version_store(store: dict):
    with open(VERSION_STORE, "w") as f:
        json.dump(store, f, indent=2)


def load_documents(docs_path: str) -> list[Document]:
    """Load all .txt and .pdf files from the policies folder."""
    documents = []

    for filepath in Path(docs_path).glob("*"):
        if filepath.suffix not in [".txt", ".pdf"]:
            continue

        if filepath.suffix == ".txt":
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

        elif filepath.suffix == ".pdf":
            from pypdf import PdfReader
            reader  = PdfReader(str(filepath))
            content = ""
            for page_num, page in enumerate(reader.pages):
                content += f"\n[Page {page_num + 1}]\n"
                content += page.extract_text() or ""

        # Detect document category from filename
        filename_lower = filepath.name.lower()
        if "vault" in filename_lower:
            category = "vault_access"
        elif "hr" in filename_lower or "handbook" in filename_lower:
            category = "hr_policy"
        elif "route" in filename_lower or "safety" in filename_lower:
            category = "route_operations"
        else:
            category = "general"

        documents.append(Document(
            page_content = content,
            metadata     = {
                "source":       filepath.name,
                "category":     category,
                "file_path":    str(filepath),
                "indexed_at":   datetime.now().isoformat(),
            }
        ))

        print(f"Loaded: {filepath.name} ({category})")

    return documents


def chunk_documents(documents: list[Document]) -> list[Document]:
    """
    Split documents into chunks.
    RecursiveCharacterTextSplitter respects sentence boundaries.
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

    print(f"\nChunked into {len(chunks)} chunks")
    print(f"Chunk size: {CHUNK_SIZE} chars | Overlap: {CHUNK_OVERLAP} chars")
    return chunks


def build_vector_store(chunks: list[Document]) -> Chroma:
    """Embed chunks and store in ChromaDB."""

    print(f"\nLoading embedding model: {EMBEDDING_MODEL}")
    print("(Runs on CPU — no GPU needed, no data leaves network)")

    embeddings = HuggingFaceEmbeddings(
        model_name      = EMBEDDING_MODEL,
        model_kwargs    = {"device": "cpu"},
        encode_kwargs   = {"normalize_embeddings": True}
    )

    # Build vector store
    print(f"Embedding {len(chunks)} chunks and storing in ChromaDB...")

    vectorstore = Chroma.from_documents(
        documents          = chunks,
        embedding          = embeddings,
        persist_directory  = CHROMA_PATH,
        collection_name    = "loomis_policies"
    )

    print(f"Vector store built at: {CHROMA_PATH}")
    print(f"Total chunks indexed: {vectorstore._collection.count()}")

    return vectorstore


def smart_ingest():
    """
    Only re-index documents that changed since last run.
    Prevents duplicate chunks — detects via file hash.
    """
    print("=" * 50)
    print("LOOMIS RAG — DOCUMENT INGESTION")
    print("=" * 50)

    version_store = load_version_store()
    changed_files = []
    skipped_files = []

    # Check which files need re-indexing
    for filepath in Path(DOCS_PATH).glob("*"):
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

    # Load only changed files
    docs_to_index = []
    for filepath in changed_files:
        if filepath.suffix == ".txt":
            with open(filepath, "r") as f:
                content = f.read()
        else:
            from pypdf import PdfReader
            reader  = PdfReader(str(filepath))
            content = "".join(
                page.extract_text() or ""
                for page in reader.pages
            )

        filename_lower = filepath.name.lower()
        category = (
            "vault_access"    if "vault"    in filename_lower else
            "hr_policy"       if "hr"       in filename_lower else
            "route_operations" if "route"   in filename_lower else
            "general"
        )

        docs_to_index.append(Document(
            page_content = content,
            metadata     = {
                "source":     filepath.name,
                "category":   category,
                "indexed_at": datetime.now().isoformat(),
            }
        ))

    # Chunk
    chunks = chunk_documents(docs_to_index)

    # Store — Chroma handles deduplication by collection
    # For production: delete old chunks for changed files first
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


if __name__ == "__main__":
    smart_ingest()