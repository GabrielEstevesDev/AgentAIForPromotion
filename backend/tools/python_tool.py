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
            print(f'![chart]({base_url}/api/charts/{{_fname}})')
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

        return "\n".join(output_parts) if output_parts else "Code executed successfully - no output."
    except subprocess.TimeoutExpired:
        return f"Error: execution timed out after {EXECUTOR_TIMEOUT_SEC} seconds."
    except Exception as exc:
        return f"Error: {exc}"
