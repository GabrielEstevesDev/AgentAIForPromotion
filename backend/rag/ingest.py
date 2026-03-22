"""
One-time ingestion script: chunks all docs/*.md files and stores them in ChromaDB.

Run from the project root:
    python -m backend.rag.ingest
"""

import io
import os
import shutil
import sys

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from ..config import (
    CHROMA_COLLECTION,
    CHROMA_DIR,
    DOCS_DIR,
    EMBEDDING_MODEL,
    OPENAI_API_KEY,
    RAG_CHUNK_OVERLAP,
    RAG_CHUNK_SIZE,
)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + chunk_size])
        start += chunk_size - overlap
    return chunks


def ingest() -> None:
    md_files = sorted(DOCS_DIR.glob("*.md"))
    if not md_files:
        print(f"No .md files found in {DOCS_DIR}")
        return

    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)

    if CHROMA_DIR.exists():
        # Clear contents instead of removing the dir (may be a Docker mount point)
        for item in CHROMA_DIR.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()


    documents: list[Document] = []
    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        chunks = chunk_text(text, RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP)
        for index, chunk in enumerate(chunks):
            documents.append(
                Document(
                    page_content=chunk,
                    metadata={"source": md_file.name, "chunk_index": index},
                )
            )

    Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        collection_name=CHROMA_COLLECTION,
        persist_directory=str(CHROMA_DIR),
    )

    print(f"Ingested {len(documents)} chunks into '{CHROMA_COLLECTION}'.")


if __name__ == "__main__":
    ingest()

