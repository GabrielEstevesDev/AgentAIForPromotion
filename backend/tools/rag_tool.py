from langchain_core.tools import tool

from ..rag.retriever import query as chroma_query


@tool
def rag_search(query: str) -> str:
    """Search the internal knowledge base (policies, shipping, returns, FAQs, guides).

    RESPONSE RULES:
    - Direct answer first, then policy excerpt labeled '**Policy:**' or '**Guidance:**'
    - End with *Source: [Document Title]*
    - Use ### headers for topics (never numbered list items as titles)
    - NEVER invent policy. If RAG shows 'guidelines' from a product guide, these are industry norms, not binding policy.
    - If no policy covers the question: 'Our knowledge base does not contain an official policy on [topic].'
    - Max 3 relevant chunks.
    """
    results = chroma_query(query)

    if not results:
        return "No relevant information found in the knowledge base."

    parts = []
    for index, result in enumerate(results, 1):
        score = result.get("relevance_score", 0)
        label = "HIGH" if score > 0.75 else "MEDIUM" if score > 0.5 else "LOW"
        parts.append(
            f"[{index}] Source: {result['source']} (Relevance: {label})\n{result['text']}"
        )

    return "\n\n---\n\n".join(parts)

