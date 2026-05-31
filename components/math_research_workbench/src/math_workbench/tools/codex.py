from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

VALID_STATUSES = {"PROVED", "CONDITIONAL", "COMPUTATIONAL", "HEURISTIC", "FAILED/OPEN"}


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.execute("pragma journal_mode=wal;")
    con.execute("pragma foreign_keys=on;")
    return con


def init_db(db_path: str, schema_path: str | None = None) -> None:
    con = connect(db_path)
    if schema_path is None:
        schema_path = str(Path(__file__).resolve().parents[3] / "data" / "schema.sql")
    con.executescript(Path(schema_path).read_text(encoding="utf-8"))
    con.commit()
    con.close()


def upsert_problem(con: sqlite3.Connection, spec: dict[str, Any]) -> int:
    cur = con.execute(
        """
        insert into problem(slug,title,domain,background_md,current_frontier_md,source_path)
        values (?,?,?,?,?,?)
        on conflict(slug) do update set
            title=excluded.title,
            domain=excluded.domain,
            background_md=excluded.background_md,
            current_frontier_md=excluded.current_frontier_md,
            source_path=excluded.source_path,
            updated_at=current_timestamp
        returning id
        """,
        (
            spec.get("slug", "problem"),
            spec.get("title", "Untitled problem"),
            spec.get("domain", "general"),
            spec.get("background", ""),
            spec.get("current_frontier", ""),
            spec.get("source_path", ""),
        ),
    )
    pid = int(cur.fetchone()[0])
    for d in spec.get("definitions", []):
        con.execute(
            "insert into definition(problem_id,name,statement_md) values (?,?,?)",
            (pid, d.get("name", "definition"), d.get("statement", "")),
        )
    con.commit()
    return pid


def upsert_strategy(con: sqlite3.Connection, strategy: dict[str, Any]) -> int:
    cur = con.execute(
        """
        insert into strategy(slug,name,rank,status,score,description_md,config_json)
        values (?,?,?,?,?,?,?)
        on conflict(slug) do update set
            name=excluded.name,
            rank=excluded.rank,
            status=excluded.status,
            score=excluded.score,
            description_md=excluded.description_md,
            config_json=excluded.config_json,
            updated_at=current_timestamp
        returning id
        """,
        (
            strategy["id"],
            strategy.get("name", strategy["id"]),
            strategy.get("rank", 100),
            strategy.get("status", "ACTIVE"),
            strategy.get("score", 0.0),
            strategy.get("description", ""),
            json.dumps(strategy),
        ),
    )
    sid = int(cur.fetchone()[0])
    con.commit()
    return sid


def insert_theorem(con: sqlite3.Connection, problem_id: int, slug: str, title: str, statement: str, status: str, frontier_rank: int | None = None) -> int:
    if status not in VALID_STATUSES:
        status = "FAILED/OPEN"
    cur = con.execute(
        """
        insert into theorem(problem_id,slug,title,statement_md,status,frontier_rank)
        values (?,?,?,?,?,?)
        on conflict(problem_id,slug) do update set
            title=excluded.title,
            statement_md=excluded.statement_md,
            status=excluded.status,
            frontier_rank=excluded.frontier_rank,
            updated_at=current_timestamp
        returning id
        """,
        (problem_id, slug, title, statement, status, frontier_rank),
    )
    tid = int(cur.fetchone()[0])
    con.commit()
    return tid


def insert_attempt(con: sqlite3.Connection, problem_id: int, run_id: str, iteration: int, strategy_id: int | None, prompt: str, result: str, status: str = "HEURISTIC", theorem_id: int | None = None) -> int:
    if status not in VALID_STATUSES:
        status = "HEURISTIC"
    cur = con.execute(
        """
        insert into attempt(problem_id,theorem_id,strategy_id,run_id,iteration,prompt_md,result_md,status)
        values (?,?,?,?,?,?,?,?) returning id
        """,
        (problem_id, theorem_id, strategy_id, run_id, iteration, prompt, result, status),
    )
    aid = int(cur.fetchone()[0])
    con.commit()
    return aid


def insert_computation(con: sqlite3.Connection, problem_id: int, run_id: str, iteration: int, name: str, report: str, status: str = "COMPUTATIONAL", theorem_id: int | None = None, code_path: str | None = None, data_path: str | None = None, report_path: str | None = None) -> int:
    cur = con.execute(
        """
        insert into computation(problem_id,theorem_id,run_id,iteration,name,code_path,data_path,report_path,summary_json,status)
        values (?,?,?,?,?,?,?,?,?,?) returning id
        """,
        (problem_id, theorem_id, run_id, iteration, name, code_path, data_path, report_path, json.dumps({"report": report[:5000]}), status),
    )
    cid = int(cur.fetchone()[0])
    con.commit()
    return cid
