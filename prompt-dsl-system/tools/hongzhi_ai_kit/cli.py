import sys
from pathlib import Path

# Add parent dir (prompt-dsl-system/tools) to path so we can import hongzhi_plugin
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Now import the standalone script as a module
try:
    import hongzhi_plugin
except ImportError:
    # Fallback if run from site-packages (future proofing)
    print("CRITICAL: hongzhi_plugin module not found.", file=sys.stderr)
    sys.exit(1)

def main():
    hongzhi_plugin.main()
