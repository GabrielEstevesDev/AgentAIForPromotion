from langchain_core.tools import tool

from ..rag.retriever import query as chroma_query


@tool
def rag_search(query: str) -> str:
    """Search the internal knowledge base for relevant information."""
    results = chroma_query(query)

    if not results:
        return "No relevant information found in the knowledge base."

    parts = []
    for index, result in enumerate(results, 1):
        parts.append(f"[{index}] Source: {result['source']}\n{result['text']}")

    return "\n\n---\n\n".join(parts)

