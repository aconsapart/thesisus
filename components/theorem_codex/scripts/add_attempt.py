from __future__ import annotations
import argparse, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from theorem_codex.db import connect, add_attempt

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--db', default='proof_codex.sqlite')
    p.add_argument('--theorem')
    p.add_argument('--strategy')
    p.add_argument('--run-id', default='manual')
    p.add_argument('--status', default='FAILED/OPEN')
    p.add_argument('--title')
    p.add_argument('--prompt-file')
    p.add_argument('--result-file')
    args = p.parse_args()
    prompt = Path(args.prompt_file).read_text() if args.prompt_file else ''
    result = Path(args.result_file).read_text() if args.result_file else ''
    con = connect(args.db)
    rowid = add_attempt(con, theorem_slug=args.theorem, strategy_slug=args.strategy, run_id=args.run_id, title=args.title, prompt_md=prompt, result_md=result, status=args.status)
    con.close()
    print(rowid)
