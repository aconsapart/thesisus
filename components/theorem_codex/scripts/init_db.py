from __future__ import annotations
import argparse, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from theorem_codex.db import init_db

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='proof_codex.sqlite')
    args = parser.parse_args()
    init_db(args.db)
    print(f'Initialized {args.db}')
