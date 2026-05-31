#!/usr/bin/env python3
"""Create or update a local settings file for Thesius Workbench.

This stores model/API configuration in config/local_settings.yaml instead of
requiring shell environment variables. The file is gitignored by default.
"""
from __future__ import annotations

import argparse
import getpass
from pathlib import Path
import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="config/local_settings.yaml")
    parser.add_argument("--model", default=None, help="Chat model name, e.g. gpt-4.1")
    parser.add_argument("--api-key", default=None, help="OpenAI API key. If omitted, prompt securely.")
    parser.add_argument("--base-url", default=None, help="Optional OpenAI-compatible API base URL")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--aristotle-api-key", default=None)
    parser.add_argument("--lean-cmd", default=None)
    parser.add_argument("--sage-cmd", default=None)
    parser.add_argument("--magma-cmd", default=None)
    parser.add_argument("--no-prompt", action="store_true", help="Do not prompt for missing API key")
    args = parser.parse_args()

    path = Path(args.path)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = {}
    if path.exists():
        existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    llm = existing.get("llm", {}) or {}
    formal = existing.get("formalization", {}) or {}
    tools = existing.get("tools", {}) or {}

    api_key = args.api_key
    if api_key is None and not args.no_prompt:
        current = llm.get("api_key", "")
        if current:
            keep = input("Existing llm.api_key found. Keep it? [Y/n] ").strip().lower()
            if keep in ("", "y", "yes"):
                api_key = current
        if api_key is None:
            api_key = getpass.getpass("OpenAI API key (input hidden, leave blank to skip): ").strip()

    if args.model is not None:
        llm["model"] = args.model
    else:
        llm.setdefault("model", "gpt-4.1")

    if api_key is not None:
        llm["api_key"] = api_key
    else:
        llm.setdefault("api_key", "")

    if args.base_url is not None:
        llm["base_url"] = args.base_url
    else:
        llm.setdefault("base_url", "")

    llm["temperature"] = args.temperature
    llm.setdefault("provider", "openai")

    if args.aristotle_api_key is not None:
        formal["aristotle_api_key"] = args.aristotle_api_key
    else:
        formal.setdefault("aristotle_api_key", "")

    if args.lean_cmd is not None:
        formal["lean_cmd"] = args.lean_cmd
    else:
        formal.setdefault("lean_cmd", "")

    formal.setdefault("aristotle_cli", "aristotle")

    if args.sage_cmd is not None:
        tools["sage_cmd"] = args.sage_cmd
    else:
        tools.setdefault("sage_cmd", "sage")

    if args.magma_cmd is not None:
        tools["magma_cmd"] = args.magma_cmd
    else:
        tools.setdefault("magma_cmd", "magma")

    config = {"llm": llm, "formalization": formal, "tools": tools}
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    path.chmod(0o600)
    print(f"Wrote local settings to {path}")
    print("This file is listed in .gitignore by default. Do not commit it.")


if __name__ == "__main__":
    main()
