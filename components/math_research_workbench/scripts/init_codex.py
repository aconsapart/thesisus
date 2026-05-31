#!/usr/bin/env python3
import argparse
from math_workbench.tools.codex import init_db

parser = argparse.ArgumentParser()
parser.add_argument("--db", required=True)
args = parser.parse_args()
init_db(args.db)
print(f"Initialized {args.db}")
