from functools import lru_cache
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from config import (
    CHROMA_DIR, CHROMA_COLLECTION,
    OPENAI_API_KEY, EMBEDDING_MODEL,
    RAG_TOP_K,
)
import os
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY


@lru_cache(maxsize=1)
def _get_vectorstore() -> Chroma:
    """Return the Chroma vectorstore (cached — initialized once per process)."""
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    return Chroma(
        collection_name=CHROMA_COLLECTION,
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DIR),
    )


def query(text: str, top_k: int = RAG_TOP_K) -> list[dict]:
    """
    Retrieve the top-k most relevant chunks for a query.

    Returns:
        [{"text": "...", "source": "03-customer-faq.md", "chunk_index": 4}, ...]
    """
    vectorstore = _get_vectorstore()
    results = vectorstore.similarity_search(text, k=top_k)
    return [
        {
            "text": doc.page_content,
            "source": doc.metadata.get("source", "unknown"),
            "chunk_index": doc.metadata.get("chunk_index", -1),
        }
        for doc in results
    ]
