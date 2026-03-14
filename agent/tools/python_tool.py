import sys
import subprocess
import textwrap
from langchain_core.tools import tool
from config import EXECUTOR_TIMEOUT_SEC


@tool
def python_executor(code: str) -> str:
    """
    Execute Python code and return stdout + stderr.

    Use this tool to:
    - Perform calculations or statistical analysis
    - Process and transform data returned by sql_query
    - Generate summaries, aggregations, or formatted reports
    - Any task that benefits from programmatic computation

    The code runs in an isolated subprocess with a 30-second timeout.
    Standard libraries are available. Print your results to stdout.

    Example:
        data = [4.5, 3.2, 5.0, 2.8, 4.1]
        avg = sum(data) / len(data)
        print(f"Average rating: {avg:.2f}")
    """
    # Dedent in case the LLM indents the whole block
    code = textwrap.dedent(code)

    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=EXECUTOR_TIMEOUT_SEC,
        )

        output_parts = []
        if result.stdout.strip():
            output_parts.append(result.stdout.strip())
        if result.stderr.strip():
            output_parts.append(f"[stderr]\n{result.stderr.strip()}")

        return "\n".join(output_parts) if output_parts else "Code executed successfully — no output."

    except subprocess.TimeoutExpired:
        return f"Error: execution timed out after {EXECUTOR_TIMEOUT_SEC} seconds."
    except Exception as e:
        return f"Error: {e}"
