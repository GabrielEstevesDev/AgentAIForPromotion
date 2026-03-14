from tools.sql_tool import sql_query
from tools.rag_tool import rag_search
from tools.search_tool import web_search
from tools.python_tool import python_executor

ALL_TOOLS = [sql_query, rag_search, web_search, python_executor]
