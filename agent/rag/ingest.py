"""
One-time ingestion script: chunks all docs/*.md files and stores them in ChromaDB.

Run from the agent/ directory:
    python -m rag.ingest

Re-running is safe — existing collection is replaced (full refresh).
"""

import sys
import io
from pathlib import Path

# Force UTF-8 output on Windows terminals
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from config import (
    DOCS_DIR, CHROMA_DIR, CHROMA_COLLECTION,
    OPENAI_API_KEY, EMBEDDING_MODEL,
    RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP,
)
import os
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start : start + chunk_size])
        start += chunk_size - overlap
    return chunks


def ingest() -> None:
    md_files = sorted(DOCS_DIR.glob("*.md"))
    if not md_files:
        print(f"No .md files found in {DOCS_DIR}")
        return

    print(f"Found {len(md_files)} documents in {DOCS_DIR}\n")

    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)

    # Delete existing persisted collection for a clean refresh
    import shutil
    if CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
        print(f"Deleted existing collection at {CHROMA_DIR}")

    documents: list[Document] = []

    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        chunks = chunk_text(text, RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP)
        for i, chunk in enumerate(chunks):
            documents.append(Document(
                page_content=chunk,
                metadata={"source": md_file.name, "chunk_index": i},
            ))
        print(f"  [ok] {md_file.name} -> {len(chunks)} chunks")

    Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        collection_name=CHROMA_COLLECTION,
        persist_directory=str(CHROMA_DIR),
    )

    print(f"\n[done] Ingestion complete - {len(documents)} chunks stored in '{CHROMA_COLLECTION}'")


if __name__ == "__main__":
    ingest()
