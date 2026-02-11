import sys
from pathlib import Path

def _load_runner():
    """Import hongzhi_plugin from installed package, fallback to source tree."""
    try:
        import hongzhi_plugin  # type: ignore

        return hongzhi_plugin
    except ImportError:
        tools_dir = Path(__file__).resolve().parent.parent
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        try:
            import hongzhi_plugin  # type: ignore

            return hongzhi_plugin
        except ImportError:
            print(
                "CRITICAL: hongzhi_plugin module not found. "
                "Run `pip install -e .` in beyond-dev-ai-kit root.",
                file=sys.stderr,
            )
            sys.exit(1)


def main():
    runner = _load_runner()
    runner.main()
