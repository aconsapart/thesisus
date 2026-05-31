from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
from thesius.app import _db_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None, help="SQLite database path. Overrides saved Thesius setting.")
    args = parser.parse_args()
    db = _db_path(args.db)
    app = Path("components/theorem_codex/apps/streamlit_app.py")
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app), "--", "--db", db], check=False)

if __name__ == "__main__":
    main()
