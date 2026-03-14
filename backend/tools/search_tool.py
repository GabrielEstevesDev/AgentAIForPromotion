import os

from langchain_tavily import TavilySearch

from ..config import TAVILY_API_KEY

os.environ["TAVILY_API_KEY"] = TAVILY_API_KEY

web_search = TavilySearch(
    max_results=5,
    name="web_search",
    description=(
        "Search the web for current or external information not available in the "
        "database or internal knowledge base."
    ),
)

