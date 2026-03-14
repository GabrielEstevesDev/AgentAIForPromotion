from langchain_core.tools import tool
from rag.retriever import query as chroma_query


@tool
def rag_search(query: str) -> str:
    """
    Search the internal knowledge base for relevant information.

    Use this tool for questions about:
    - Shipping and return policies
    - Order lifecycle and statuses
    - Customer FAQs
    - Product category guides and buying advice
    - Technical glossary and product specifications
    - Review and rating policies
    - Promotions, bundles, and discount rules
    - AI assistant capabilities and limitations
    - Platform trends and analytics reports

    Returns the most relevant excerpts with their source document.
    """
    results = chroma_query(query)

    if not results:
        return "No relevant information found in the knowledge base."

    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"[{i}] Source: {r['source']}\n{r['text']}")

    return "\n\n---\n\n".join(parts)
