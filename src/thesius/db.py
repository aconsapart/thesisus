from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

VALID_THEOREM_STATUSES = {"PROVED", "CONDITIONAL", "COMPUTATIONAL", "HEURISTIC", "FAILED/OPEN", "FALSIFIED"}
VALID_STRATEGY_STATUSES = {"ACTIVE", "DEMOTED", "PAUSED", "RESOLVED", "FAILED/OPEN"}

SCHEMA_SQL = r'''
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS theorem (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    statement_md TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN','FALSIFIED')),
    kind TEXT NOT NULL DEFAULT 'THEOREM',
    frontier_rank INTEGER,
    is_frontier INTEGER NOT NULL DEFAULT 0,
    importance INTEGER NOT NULL DEFAULT 3,
    parent_id INTEGER REFERENCES theorem(id),
    confidence REAL DEFAULT 0.0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS theorem_relation (
    id INTEGER PRIMARY KEY,
    source_theorem_id INTEGER NOT NULL REFERENCES theorem(id) ON DELETE CASCADE,
    target_theorem_id INTEGER NOT NULL REFERENCES theorem(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL DEFAULT 'DEPENDS_ON',
    note_md TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_theorem_id, target_theorem_id, relation_type)
);
CREATE TABLE IF NOT EXISTS claim (
    id INTEGER PRIMARY KEY,
    theorem_id INTEGER NOT NULL REFERENCES theorem(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN','FALSIFIED')),
    claim_md TEXT NOT NULL,
    proof_sketch_md TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS strategy (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description_md TEXT NOT NULL,
    rank INTEGER,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    score REAL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS attempt (
    id INTEGER PRIMARY KEY,
    theorem_id INTEGER REFERENCES theorem(id) ON DELETE SET NULL,
    strategy_id INTEGER REFERENCES strategy(id) ON DELETE SET NULL,
    run_id TEXT NOT NULL,
    title TEXT,
    prompt_md TEXT NOT NULL,
    result_md TEXT NOT NULL,
    model TEXT,
    status TEXT NOT NULL CHECK (status IN ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN','FALSIFIED')),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS falsification (
    id INTEGER PRIMARY KEY,
    theorem_id INTEGER REFERENCES theorem(id) ON DELETE SET NULL,
    strategy_id INTEGER REFERENCES strategy(id) ON DELETE SET NULL,
    obstruction_md TEXT NOT NULL,
    counterexample_md TEXT,
    severity TEXT CHECK (severity IN ('LOW','MEDIUM','HIGH','KILLS_STRATEGY')) DEFAULT 'MEDIUM',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS computation (
    id INTEGER PRIMARY KEY,
    theorem_id INTEGER REFERENCES theorem(id) ON DELETE SET NULL,
    run_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN','FALSIFIED')),
    code_path TEXT,
    data_path TEXT,
    report_path TEXT,
    summary_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS formalization_job (
    id INTEGER PRIMARY KEY,
    theorem_id INTEGER REFERENCES theorem(id) ON DELETE SET NULL,
    backend TEXT NOT NULL,
    status TEXT NOT NULL,
    lean_path TEXT,
    prompt_md TEXT,
    result_md TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS artifact (
    id INTEGER PRIMARY KEY,
    theorem_id INTEGER REFERENCES theorem(id) ON DELETE SET NULL,
    attempt_id INTEGER REFERENCES attempt(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT,
    description_md TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tag (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, description TEXT);
CREATE TABLE IF NOT EXISTS theorem_tag (theorem_id INTEGER NOT NULL REFERENCES theorem(id) ON DELETE CASCADE, tag_id INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE, PRIMARY KEY(theorem_id, tag_id));
CREATE VIEW IF NOT EXISTS v_current_frontier AS SELECT id, slug, title, status, kind, frontier_rank, importance, updated_at FROM theorem WHERE is_frontier=1 ORDER BY frontier_rank ASC, importance DESC;
CREATE VIEW IF NOT EXISTS v_status_counts AS SELECT status, count(*) count FROM theorem GROUP BY status;
CREATE VIEW IF NOT EXISTS v_recent_attempts AS SELECT a.id, a.created_at, t.slug theorem, s.slug strategy, a.status, a.run_id, a.title, a.model FROM attempt a LEFT JOIN theorem t ON t.id=a.theorem_id LEFT JOIN strategy s ON s.id=a.strategy_id ORDER BY a.created_at DESC;
CREATE VIEW IF NOT EXISTS v_strategy_health AS SELECT s.id, s.slug, s.name, s.status, s.rank, s.score, count(a.id) attempts, sum(case when a.status='PROVED' then 1 else 0 end) proved_attempts, sum(case when a.status='FAILED/OPEN' then 1 else 0 end) open_attempts FROM strategy s LEFT JOIN attempt a ON a.strategy_id=s.id GROUP BY s.id;
CREATE VIEW IF NOT EXISTS v_dependency_edges AS SELECT tr.id, src.slug theorem, tr.relation_type, tgt.slug depends_on, tr.note_md FROM theorem_relation tr JOIN theorem src ON src.id=tr.source_theorem_id JOIN theorem tgt ON tgt.id=tr.target_theorem_id;
'''

SEED_THEOREMS = [
    {
        "slug": "exact-short-box-product-fiber-curve-intersection",
        "title": "Exact Short-Box Product-Fiber Curve-Intersection Theorem",
        "status": "FAILED/OPEN",
        "kind": "FRONTIER",
        "frontier_rank": 1,
        "is_frontier": True,
        "importance": 5,
        "statement_md": "Prove random-sized second-moment bounds for intersections of the exact (A,B)-image of short prime boxes with off-identity product-fiber curves M_{p1,q1}M_{p2,q2}~R, retaining both A=2(q+1)-p(q-2) and B=2(p+1)(q+1).",
    },
    {
        "slug": "very-short-shifted-product-character-sum",
        "title": "Very-Short Shifted-Product Character-Sum Theorem",
        "status": "FAILED/OPEN",
        "kind": "FRONTIER",
        "frontier_rank": 2,
        "is_frontier": True,
        "importance": 4,
        "statement_md": "For non-square rational quadratic F from off-identity product fibers, control sums over p~P,q~Q of chi(F(2(p+1)(q+1))) in PQ <= ell polylog(X), with necessary size/averaging hypotheses.",
    },
    {
        "slug": "final-average-bound",
        "title": "Final Average Bound",
        "status": "CONDITIONAL",
        "kind": "THEOREM",
        "frontier_rank": 99,
        "is_frontier": False,
        "importance": 5,
        "statement_md": "Show sum_{n<=X} A(n) << X(log X)^C, hence S(X)<<X(log X)^C. Currently conditional on resolving the final rank-two core.",
    },
]

SEED_STRATEGIES = [
    ("hybrid-combined-attack", "Hybrid combined attack", "Combine integer hyperbola, finite-field shifted products, exact (A,B)-curve incidence, near-injectivity, and divisor-window rigidity.", 1, "ACTIVE", 10.0),
    ("exact-product-fiber-incidence", "Exact product-fiber incidence", "Attack M_{p1,q1}M_{p2,q2}~R retaining A and B constraints.", 2, "ACTIVE", 9.5),
    ("very-short-shifted-product", "Very-short shifted-product character sums", "Attack chi(F(2(p+1)(q+1))) in the very-short branch.", 3, "ACTIVE", 8.5),
    ("near-injectivity", "Near-injectivity / collision energy", "Prove K(mpq) has random-sized collision energy.", 4, "ACTIVE", 7.5),
    ("meta-strategy-discovery", "Meta strategy discovery", "Generate and falsify materially new strategies before adding them.", 5, "ACTIVE", 7.0),
]


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def init_db(db_path: str | Path) -> None:
    con = connect(db_path)
    try:
        con.executescript(SCHEMA_SQL)
        con.commit()
    finally:
        con.close()


def table_count(con: sqlite3.Connection, table: str) -> int:
    return int(con.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


def theorem_id(con: sqlite3.Connection, slug: str) -> int | None:
    row = con.execute("SELECT id FROM theorem WHERE slug=?", (slug,)).fetchone()
    return None if row is None else int(row[0])


def strategy_id(con: sqlite3.Connection, slug: str) -> int | None:
    row = con.execute("SELECT id FROM strategy WHERE slug=?", (slug,)).fetchone()
    return None if row is None else int(row[0])


def upsert_theorem(con: sqlite3.Connection, *, slug: str, title: str, statement_md: str, status: str = "FAILED/OPEN", kind: str = "THEOREM", frontier_rank: int | None = None, is_frontier: bool = False, importance: int = 3, confidence: float = 0.0) -> int:
    if status not in VALID_THEOREM_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    row = con.execute(
        """
        INSERT INTO theorem(slug,title,statement_md,status,kind,frontier_rank,is_frontier,importance,confidence)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(slug) DO UPDATE SET
            title=excluded.title,
            statement_md=excluded.statement_md,
            status=excluded.status,
            kind=excluded.kind,
            frontier_rank=excluded.frontier_rank,
            is_frontier=excluded.is_frontier,
            importance=excluded.importance,
            confidence=excluded.confidence,
            updated_at=CURRENT_TIMESTAMP
        RETURNING id
        """,
        (slug, title, statement_md, status, kind, frontier_rank, int(is_frontier), importance, confidence),
    ).fetchone()
    con.commit()
    return int(row[0])


def upsert_strategy(con: sqlite3.Connection, *, slug: str, name: str, description_md: str, rank: int | None = None, status: str = "ACTIVE", score: float = 0.0) -> int:
    row = con.execute(
        """
        INSERT INTO strategy(slug,name,description_md,rank,status,score)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(slug) DO UPDATE SET
            name=excluded.name,
            description_md=excluded.description_md,
            rank=excluded.rank,
            status=excluded.status,
            score=excluded.score,
            updated_at=CURRENT_TIMESTAMP
        RETURNING id
        """,
        (slug, name, description_md, rank, status, score),
    ).fetchone()
    con.commit()
    return int(row[0])


def seed(db_path: str | Path) -> None:
    init_db(db_path)
    con = connect(db_path)
    try:
        for thm in SEED_THEOREMS:
            upsert_theorem(con, **thm)
        for slug, name, desc, rank, status, score in SEED_STRATEGIES:
            upsert_strategy(con, slug=slug, name=name, description_md=desc, rank=rank, status=status, score=score)
    finally:
        con.close()


def add_attempt(con: sqlite3.Connection, *, theorem_slug: str | None, strategy_slug: str | None, run_id: str, title: str | None, prompt_md: str, result_md: str, status: str, model: str | None = None) -> int:
    if status not in VALID_THEOREM_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    tid = theorem_id(con, theorem_slug) if theorem_slug else None
    sid = strategy_id(con, strategy_slug) if strategy_slug else None
    row = con.execute(
        "INSERT INTO attempt(theorem_id,strategy_id,run_id,title,prompt_md,result_md,status,model) VALUES (?,?,?,?,?,?,?,?) RETURNING id",
        (tid, sid, run_id, title, prompt_md, result_md, status, model),
    ).fetchone()
    con.commit()
    return int(row[0])


def add_falsification(con: sqlite3.Connection, *, theorem_slug: str | None, strategy_slug: str | None, obstruction_md: str, counterexample_md: str | None = None, severity: str = "MEDIUM") -> int:
    tid = theorem_id(con, theorem_slug) if theorem_slug else None
    sid = strategy_id(con, strategy_slug) if strategy_slug else None
    row = con.execute(
        "INSERT INTO falsification(theorem_id,strategy_id,obstruction_md,counterexample_md,severity) VALUES (?,?,?,?,?) RETURNING id",
        (tid, sid, obstruction_md, counterexample_md, severity),
    ).fetchone()
    con.commit()
    return int(row[0])


def add_artifact(con: sqlite3.Connection, *, path: str, kind: str = "file", theorem_slug: str | None = None, attempt_id: int | None = None, description_md: str | None = None) -> int:
    p = Path(path)
    sha = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() and p.is_file() else None
    tid = theorem_id(con, theorem_slug) if theorem_slug else None
    row = con.execute(
        "INSERT INTO artifact(theorem_id,attempt_id,kind,path,sha256,description_md) VALUES (?,?,?,?,?,?) RETURNING id",
        (tid, attempt_id, kind, str(path), sha, description_md),
    ).fetchone()
    con.commit()
    return int(row[0])


def rows(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    con.row_factory = sqlite3.Row
    return list(con.execute(sql, params))
