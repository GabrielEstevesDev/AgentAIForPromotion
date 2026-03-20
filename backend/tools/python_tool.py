import subprocess
import sys
import textwrap
import time

from langchain_core.tools import tool

from ..config import BACKEND_BASE_URL, CHARTS_DIR, EXECUTOR_TIMEOUT_SEC

# Force non-interactive matplotlib backend before any user imports
_CHART_PREAMBLE = """\
import sys as _sys, io as _io
try:
    import matplotlib as _matplotlib
    _matplotlib.use('Agg')
    import matplotlib.pyplot as _plt
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False
"""


def _build_postamble(charts_dir: str, base_url: str) -> str:
    """Build chart-capture code that saves PNGs to disk and prints their URLs."""
    return f"""
if _HAS_MPL:
    try:
        import os as _os, uuid as _uuid
        _figs = [_plt.figure(i) for i in _plt.get_fignums()]
        for _fig in _figs:
            _fname = str(_uuid.uuid4()) + '.png'
            _fpath = _os.path.join({str(charts_dir)!r}, _fname)
            _fig.savefig(_fpath, format='png', bbox_inches='tight', dpi=150)
            print(f'![chart](/api/charts/{{_fname}})')
        _plt.close('all')
    except Exception as _e:
        print(f'[chart capture error] {{_e}}')
"""


def _cleanup_old_charts(max_age_seconds: int = 3600) -> None:
    """Remove chart PNGs older than max_age_seconds."""
    now = time.time()
    for f in CHARTS_DIR.glob("*.png"):
        try:
            if now - f.stat().st_mtime > max_age_seconds:
                f.unlink()
        except OSError:
            pass


@tool
def python_executor(code: str) -> str:
    """Execute Python code and return stdout plus stderr.
    Matplotlib charts are automatically captured and returned as inline markdown images.
    To produce a chart: import matplotlib.pyplot as plt, build the plot, call plt.tight_layout() — do NOT call plt.show().

    DATA HANDLING: Always define your data directly as Python lists or dicts using the
    exact values from previous tool calls (sql_query or query_library).
    NEVER import sqlite3 or connect to any database in your Python code.
    The data must be hardcoded in the script.

    CHART STANDARDS:
    - plt.style.use('seaborn-v0_8-whitegrid')
    - Descriptive title: plt.title('Revenue by Category – Last 12 Months')
    - Labeled axes with units
    - plt.tight_layout()
    - Thousands separator for large numbers
    - ONE chart per response. No charts in HITL pre-approval.
    - SORTING: If x-axis is dates/months/time → ALWAYS sort chronologically ascending (oldest left, newest right). NEVER sort time-series by value. Only sort by value when x-axis is a non-time category (product names, categories).
    - Do NOT call plt.savefig() or plt.show() — chart capture is fully automatic.

    CRITICAL: You MUST call python_executor to create charts. Never write markdown image links like ![chart](attachment://...) — they don't work.

    After execution, this tool returns a ![chart](/api/charts/...) link — include this EXACT link in your response.
    """
    _cleanup_old_charts()
    code = textwrap.dedent(code)
    postamble = _build_postamble(str(CHARTS_DIR), BACKEND_BASE_URL)
    wrapped = _CHART_PREAMBLE + code + postamble

    try:
        result = subprocess.run(
            [sys.executable, "-c", wrapped],
            capture_output=True,
            text=True,
            timeout=EXECUTOR_TIMEOUT_SEC,
        )

        output_parts = []
        if result.stdout.strip():
            output_parts.append(result.stdout.strip())
        if result.stderr.strip():
            output_parts.append(f"[stderr]\n{result.stderr.strip()}")

        result = "\n".join(output_parts) if output_parts else "Code executed successfully - no output."

        # If a chart was generated, append insight hint to guide concise commentary
        if "![chart]" in result:
            result += (
                "\n\n[CHART GENERATED — write exactly 1 INSIGHT line "
                "(what pattern the chart shows) and 1 ACTION line "
                "(what to do about it), then stop. No other commentary.]"
            )

        return result
    except subprocess.TimeoutExpired:
        return f"Error: execution timed out after {EXECUTOR_TIMEOUT_SEC} seconds."
    except Exception as exc:
        return f"Error: {exc}"
