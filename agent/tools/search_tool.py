from langchain_tavily import TavilySearch
from config import TAVILY_API_KEY
import os

os.environ["TAVILY_API_KEY"] = TAVILY_API_KEY

web_search = TavilySearch(
    max_results=5,
    name="web_search",
    description=(
        "Search the web for current or external information not available in the "
        "database or internal knowledge base. Use for: market trends, competitor info, "
        "product specs from manufacturer sites, current news, or anything requiring "
        "up-to-date external data."
    ),
)
