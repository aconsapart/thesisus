from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
from thesius.app import _db_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None, help="SQLite database path. Overrides saved Thesius setting.")
    args = parser.parse_args()
    db = _db_path(args.db)
    metadata = Path("components/theorem_codex/datasette/metadata.json")
    cmd = [sys.executable, "-m", "datasette", "serve", db]
    if metadata.exists():
        cmd += ["--metadata", str(metadata)]
    subprocess.run(cmd, check=False)

if __name__ == "__main__":
    main()
