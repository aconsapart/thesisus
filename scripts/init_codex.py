from __future__ import annotations
import argparse
from thesius.app import _db_path
from thesius.db import seed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None, help="SQLite database path. Overrides saved Thesius setting.")
    args = parser.parse_args()
    db = _db_path(args.db)
    seed(db)
    print(f"Initialized {db}")

if __name__ == "__main__":
    main()
