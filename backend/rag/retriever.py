import os
from functools import lru_cache

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from ..config import (
    CHROMA_COLLECTION,
    CHROMA_DIR,
    EMBEDDING_MODEL,
    OPENAI_API_KEY,
    RAG_TOP_K,
)

os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY


@lru_cache(maxsize=1)
def _get_vectorstore() -> Chroma:
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    return Chroma(
        collection_name=CHROMA_COLLECTION,
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DIR),
    )


def query(text: str, top_k: int = RAG_TOP_K) -> list[dict]:
    vectorstore = _get_vectorstore()
    results = vectorstore.similarity_search_with_relevance_scores(text, k=top_k)
    return [
        {
            "text": doc.page_content,
            "source": doc.metadata.get("source", "unknown"),
            "chunk_index": doc.metadata.get("chunk_index", -1),
            "relevance_score": round(score, 3),
        }
        for doc, score in results
    ]

