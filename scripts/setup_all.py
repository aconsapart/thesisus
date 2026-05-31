from __future__ import annotations
import subprocess, sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    print("Installing unified requirements...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(root / "requirements-unified.txt")])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-e", str(root)])
    for comp in ["components/math_research_workbench", "components/math_frontier_langchain_template"]:
        p = root / comp
        if (p / "pyproject.toml").exists():
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-e", str(p)])
    print("Setup complete. Use: python -m thesius status")

if __name__ == "__main__":
    main()
