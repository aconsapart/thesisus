from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=4)
    parser.add_argument("--parallel-strategies", type=int, default=4)
    parser.add_argument("--out", default="runs/erdos_hybrid_run")
    args = parser.parse_args()
    script = Path("components/erdos_hybrid_strategy_agent/src/erdos_agent.py")
    cmd = [sys.executable, str(script), "--iterations", str(args.iterations), "--parallel-strategies", str(args.parallel_strategies), "--out", args.out]
    subprocess.run(cmd, check=False)

if __name__ == "__main__":
    main()
