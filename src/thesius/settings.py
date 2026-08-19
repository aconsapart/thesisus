from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

DEFAULT_DB = "proof_codex.sqlite"
CONFIG_PATH = Path(os.environ.get("THESIUS_CONFIG", "config/local_cli_settings.json"))


def load_settings(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Match app.py's tolerance: a corrupt config falls back to defaults
        # instead of crashing some subcommands and not others.
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_settings(data: dict[str, Any], path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def nested_get(data: dict[str, Any], dotted_key: str) -> Any:
    cur: Any = data
    for part in dotted_key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def nested_set(data: dict[str, Any], dotted_key: str, value: Any) -> None:
    cur: dict[str, Any] = data
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def get_setting(dotted_key: str, default: Any = None) -> Any:
    data = load_settings()
    val = nested_get(data, dotted_key)
    return default if val is None else val


def set_setting(dotted_key: str, value: Any) -> None:
    data = load_settings()
    nested_set(data, dotted_key, value)
    save_settings(data)


TRUTHY_VALUES = {"1", "true", "yes", "on"}


def feature_enabled(name: str, default: bool = False) -> bool:
    """Check a feature flag.

    Resolution order:
    1. THESIUS_FEATURE_<NAME> environment variable,
    2. features.<name> in config/local_cli_settings.json,
    3. the provided default.
    """
    env = os.environ.get(f"THESIUS_FEATURE_{name.upper()}")
    if env is not None:
        return env.strip().lower() in TRUTHY_VALUES
    value = get_setting(f"features.{name}")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_VALUES
    return default


def get_database_path(cli_db: Optional[str] = None) -> str:
    """Resolve the SQLite database path.

    Priority (identical to app.py's _db_path):
    1. explicit CLI --db value
    2. config/local_cli_settings.json keys: database.path, database_path,
       db_path, database, or db
    3. THESIUS_DB environment variable
    4. DEFAULT_DB
    """
    if cli_db:
        return cli_db

    data = load_settings()
    for key in ("database.path", "database_path", "db_path", "database", "db"):
        val = nested_get(data, key) if "." in key else data.get(key)
        if val and not isinstance(val, dict):
            return str(val)

    env = os.environ.get("THESIUS_DB")
    if env:
        return env

    return DEFAULT_DB


def set_database_path(path: str) -> None:
    data = load_settings()
    nested_set(data, "database.path", path)
    # Keep legacy flat keys for easy grepping/backwards compatibility.
    data["database_path"] = path
    data["db_path"] = path
    save_settings(data)


def get_db_path(cli_db: Optional[str] = None) -> str:
    """Backward-compatible alias for get_database_path."""
    return get_database_path(cli_db)
