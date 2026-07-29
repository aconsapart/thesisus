"""Bring an existing codex database up to the counterexample-aware schema.

`schema.sql` is written with `create table if not exists`, so re-running it on a
database created before this refactor is a no-op: the old `check(status in
(...))` constraints survive and reject `FALSIFIED`.  SQLite cannot alter a CHECK
constraint, so the affected tables are rebuilt following the procedure in the
SQLite documentation for "other kinds of table schema changes".

The migration is idempotent and reports exactly what it touched, so a run that
silently does nothing is distinguishable from a run that had nothing to do.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

__all__ = ["MigrationReport", "migrate", "pending_migrations"]

# Tables whose status CHECK constraint must learn about FALSIFIED.
STATUS_TABLES = ("theorem", "claim", "attempt", "computation")

# Columns added to pre-existing tables; ALTER TABLE ADD COLUMN is safe for these.
ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "falsification": [("run_id", "text"), ("iteration", "integer")],
}

_STATUS_CHECK = re.compile(r"(check\s*\(\s*status\s+in\s*\([^)]*)\)", re.IGNORECASE)


@dataclass
class MigrationReport:
    rebuilt_tables: list[str] = field(default_factory=list)
    added_columns: list[str] = field(default_factory=list)
    already_current: bool = False
    foreign_key_violations: list[Any] = field(default_factory=list)

    def summary(self) -> str:
        if self.already_current:
            return "codex schema already current; nothing to migrate"
        parts = []
        if self.rebuilt_tables:
            parts.append("rebuilt " + ", ".join(self.rebuilt_tables) + " to accept FALSIFIED")
        if self.added_columns:
            parts.append("added columns " + ", ".join(self.added_columns))
        if self.foreign_key_violations:
            parts.append(f"WARNING: {len(self.foreign_key_violations)} foreign key violation(s) after migration")
        return "; ".join(parts) or "nothing to migrate"


def _table_sql(con: sqlite3.Connection, table: str) -> str | None:
    row = con.execute(
        "select sql from sqlite_master where type='table' and name=?", (table,)
    ).fetchone()
    return row[0] if row and row[0] else None


def _columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in con.execute(f"pragma table_info({table})")]


def pending_migrations(con: sqlite3.Connection) -> dict[str, list[str]]:
    """What this database still needs, without changing anything."""
    rebuild = []
    for table in STATUS_TABLES:
        sql = _table_sql(con, table)
        if not sql or "'FALSIFIED'" in sql:
            continue
        # Only a status CHECK constraint can reject FALSIFIED. A free-text
        # status column already accepts it and must not be rebuilt -- this
        # detector has to flag exactly what `_rebuild_status_table` can handle,
        # or migrate() raises on a database it should have left alone.
        if _STATUS_CHECK.search(sql):
            rebuild.append(table)
    add: list[str] = []
    for table, columns in ADDED_COLUMNS.items():
        if _table_sql(con, table) is None:
            continue
        existing = set(_columns(con, table))
        add.extend(f"{table}.{name}" for name, _type in columns if name not in existing)
    return {"rebuild": rebuild, "add_columns": add}


def _rebuild_status_table(con: sqlite3.Connection, table: str) -> None:
    original = _table_sql(con, table)
    if original is None:  # pragma: no cover - caller checks
        return
    if not _STATUS_CHECK.search(original):
        raise RuntimeError(
            f"cannot migrate {table!r}: no recognisable status CHECK constraint. "
            "Migrate this table by hand rather than guessing at its DDL."
        )
    new_sql = _STATUS_CHECK.sub(lambda m: m.group(1) + ",'FALSIFIED')", original, count=1)
    temp = f"{table}__migrated"
    new_sql = re.sub(
        rf"create\s+table\s+(if\s+not\s+exists\s+)?[\"'`\[]?{table}[\"'`\]]?",
        f"create table {temp}",
        new_sql,
        count=1,
        flags=re.IGNORECASE,
    )
    columns = _columns(con, table)
    column_list = ", ".join(f'"{c}"' for c in columns)
    con.execute(new_sql)
    con.execute(f"insert into {temp} ({column_list}) select {column_list} from {table}")
    con.execute(f"drop table {table}")
    con.execute("pragma legacy_alter_table = on")
    con.execute(f"alter table {temp} rename to {table}")
    con.execute("pragma legacy_alter_table = off")


def migrate(con: sqlite3.Connection) -> MigrationReport:
    """Apply every pending migration. Safe to call on every startup."""
    report = MigrationReport()
    pending = pending_migrations(con)
    if not pending["rebuild"] and not pending["add_columns"]:
        report.already_current = True
        return report

    con.commit()
    con.execute("pragma foreign_keys = off")
    try:
        con.execute("begin")
        for table in pending["rebuild"]:
            _rebuild_status_table(con, table)
            report.rebuilt_tables.append(table)
        for table, columns in ADDED_COLUMNS.items():
            if _table_sql(con, table) is None:
                continue
            existing = set(_columns(con, table))
            for name, ctype in columns:
                if name not in existing:
                    con.execute(f"alter table {table} add column {name} {ctype}")
                    report.added_columns.append(f"{table}.{name}")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        report.foreign_key_violations = list(con.execute("pragma foreign_key_check"))
        con.execute("pragma foreign_keys = on")
    return report
