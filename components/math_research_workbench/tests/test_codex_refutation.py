"""Tests for the refutation ledger: schema, migration, and the write path.

Before this refactor the `falsification` table existed but had no writer, so the
dashboard's Falsifications tab could only ever be empty. These tests pin down
that it now fills, and that nothing weaker than a checked witness can get in.
"""

from __future__ import annotations

import sqlite3

import pytest

from math_workbench.conjecture import Conjecture
from math_workbench.tools import codex
from math_workbench.tools.migrate import migrate, pending_migrations
from math_workbench.tools.refutation import Witness, search_conjecture

LEGACY_SCHEMA = """
create table problem (id integer primary key, slug text unique not null, title text not null,
  domain text, background_md text, current_frontier_md text, source_path text,
  created_at text, updated_at text);
create table theorem (id integer primary key, problem_id integer references problem(id),
  slug text not null, title text not null, statement_md text not null,
  status text not null check(status in ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN')),
  frontier_rank integer, parent_id integer references theorem(id),
  created_at text, updated_at text, unique(problem_id, slug));
create table attempt (id integer primary key, problem_id integer, theorem_id integer, strategy_id integer,
  run_id text not null, iteration integer, prompt_md text not null, result_md text not null,
  status text not null check(status in ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN')),
  created_at text);
create table falsification (id integer primary key, problem_id integer, theorem_id integer,
  strategy_id integer, obstruction_md text not null, counterexample_md text,
  severity text default 'MEDIUM', created_at text);
"""


@pytest.fixture
def fresh_db(tmp_path) -> str:
    path = str(tmp_path / "codex.sqlite")
    codex.init_db(path)
    return path


@pytest.fixture
def euler() -> Conjecture:
    return Conjecture.from_dict(
        {
            "id": "euler-poly",
            "statement": "n^2 + n + 41 is prime for all n",
            "predicate": "is_prime(n*n + n + 41)",
            "variables": {"n": {"kind": "integers", "low": 0, "high": 45}},
        }
    )


# --------------------------------------------------------------------------
# Migration.
# --------------------------------------------------------------------------


def test_legacy_database_rejects_falsified_before_migration(tmp_path):
    path = str(tmp_path / "legacy.sqlite")
    con = sqlite3.connect(path)
    con.executescript(LEGACY_SCHEMA)
    con.execute("insert into problem(slug,title) values ('p','Legacy')")
    con.execute("insert into theorem(problem_id,slug,title,statement_md,status) values (1,'t','T','S','FAILED/OPEN')")
    con.commit()
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("update theorem set status='FALSIFIED'")
    con.close()


def test_migration_rebuilds_constraints_and_preserves_rows(tmp_path):
    path = str(tmp_path / "legacy.sqlite")
    con = sqlite3.connect(path)
    con.executescript(LEGACY_SCHEMA)
    con.execute("insert into problem(slug,title) values ('p','Legacy')")
    con.execute("insert into theorem(problem_id,slug,title,statement_md,status) values (1,'t','Keep me','S','PROVED')")
    con.commit()
    con.close()

    report = codex.init_db(path)
    assert "theorem" in report.rebuilt_tables
    assert "falsification.run_id" in report.added_columns
    assert report.foreign_key_violations == []

    con = codex.connect(path)
    assert con.execute("select title, status from theorem").fetchone() == ("Keep me", "PROVED")
    con.execute("update theorem set status='FALSIFIED'")
    con.commit()
    assert con.execute("select status from theorem").fetchone()[0] == "FALSIFIED"
    con.close()


def test_migration_is_idempotent(tmp_path):
    path = str(tmp_path / "legacy.sqlite")
    con = sqlite3.connect(path)
    con.executescript(LEGACY_SCHEMA)
    con.commit()
    con.close()

    codex.init_db(path)
    second = codex.init_db(path)
    assert second.already_current
    assert second.rebuilt_tables == []

    con = codex.connect(path)
    assert pending_migrations(con) == {"rebuild": [], "add_columns": []}
    con.close()


def test_fresh_database_needs_no_migration(fresh_db):
    con = codex.connect(fresh_db)
    assert pending_migrations(con) == {"rebuild": [], "add_columns": []}
    con.close()


def test_a_status_column_with_no_check_constraint_is_left_alone(tmp_path):
    """It already accepts FALSIFIED, so rebuilding it would be pure risk.

    The detector must flag exactly what the rebuilder can handle: flagging this
    table would send `migrate` into DDL it cannot parse and abort the upgrade.
    """
    path = str(tmp_path / "odd.sqlite")
    con = sqlite3.connect(path)
    con.executescript("create table theorem (id integer primary key, status text not null);")
    con.commit()
    assert pending_migrations(con)["rebuild"] == []
    assert migrate(con).already_current

    con.execute("insert into theorem(status) values ('FALSIFIED')")
    con.commit()
    con.close()


# --------------------------------------------------------------------------
# Writing refutations.
# --------------------------------------------------------------------------


def test_search_outcome_round_trips_into_the_ledger(fresh_db, euler):
    con = codex.connect(fresh_db)
    problem_id = codex.upsert_problem(con, {"slug": "p", "title": "P"})
    outcome = search_conjecture(euler)

    result = codex.record_search_outcome(con, problem_id, euler, outcome, run_id="r", iteration=0)
    assert result["status"] == "FALSIFIED"
    assert result["falsification_id"] is not None

    status = con.execute("select status from conjecture where slug='euler-poly'").fetchone()[0]
    assert status == "FALSIFIED"

    rows = codex.verified_counterexamples(con, problem_id)
    assert rows, "a verified witness must reach the ledger"
    assert any(r["witness_md"] == "n = 40" for r in rows)

    # The falsification table now actually fills.
    severity, text = con.execute("select severity, counterexample_md from falsification").fetchone()
    assert severity == "KILLS_STRATEGY"
    assert "n = 40" in text
    con.close()


def test_recording_the_same_witness_twice_does_not_duplicate_it(fresh_db, euler):
    con = codex.connect(fresh_db)
    problem_id = codex.upsert_problem(con, {"slug": "p", "title": "P"})
    outcome = search_conjecture(euler)
    codex.record_search_outcome(con, problem_id, euler, outcome, run_id="r1", iteration=0)
    before = con.execute("select count(*) from counterexample").fetchone()[0]
    codex.record_search_outcome(con, problem_id, euler, outcome, run_id="r2", iteration=1)
    assert con.execute("select count(*) from counterexample").fetchone()[0] == before
    con.close()


def test_a_rejected_witness_is_stored_as_rejected_and_excluded_from_the_verified_view(fresh_db, euler):
    con = codex.connect(fresh_db)
    problem_id = codex.upsert_problem(con, {"slug": "p", "title": "P"})
    conjecture_id = codex.upsert_conjecture(con, problem_id, euler)
    codex.insert_counterexample(
        con,
        problem_id,
        conjecture_id,
        Witness("euler-poly", {"n": 7}, "REJECTED", detail="the predicate holds here"),
    )
    assert con.execute("select count(*) from counterexample").fetchone()[0] == 1
    assert codex.verified_counterexamples(con, problem_id) == []
    board = con.execute("select discarded_claims, verified_counterexamples from v_conjecture_board").fetchone()
    assert board == (1, 0)
    con.close()


def test_an_unknown_verification_verdict_is_refused(fresh_db, euler):
    con = codex.connect(fresh_db)
    problem_id = codex.upsert_problem(con, {"slug": "p", "title": "P"})
    conjecture_id = codex.upsert_conjecture(con, problem_id, euler)
    with pytest.raises(ValueError, match="unknown verification"):
        codex.insert_counterexample(
            con, problem_id, conjecture_id, Witness("euler-poly", {"n": 40}, "DEFINITELY_TRUE")
        )
    con.close()


def test_an_unknown_conjecture_status_is_refused(fresh_db, euler):
    con = codex.connect(fresh_db)
    problem_id = codex.upsert_problem(con, {"slug": "p", "title": "P"})
    conjecture_id = codex.upsert_conjecture(con, problem_id, euler)
    with pytest.raises(ValueError, match="unknown conjecture status"):
        codex.set_conjecture_status(con, conjecture_id, "MOSTLY_TRUE")
    con.close()


def test_theorem_ledger_accepts_falsified(fresh_db):
    con = codex.connect(fresh_db)
    problem_id = codex.upsert_problem(con, {"slug": "p", "title": "P"})
    codex.insert_theorem(con, problem_id, "t", "T", "statement", "FALSIFIED", 0)
    assert con.execute("select status from theorem where slug='t'").fetchone()[0] == "FALSIFIED"
    con.close()


def test_exhaustively_verified_conjecture_is_recorded_with_no_witnesses(fresh_db):
    con = codex.connect(fresh_db)
    problem_id = codex.upsert_problem(con, {"slug": "p", "title": "P"})
    c = Conjecture.from_dict(
        {
            "id": "totient-even",
            "statement": "phi(n) is even for n > 2",
            "predicate": "totient(n) % 2 == 0",
            "assumptions": ["n > 2"],
            "variables": {"n": {"kind": "integers", "low": 1, "high": 100}},
        }
    )
    outcome = search_conjecture(c)
    codex.record_search_outcome(con, problem_id, c, outcome)
    row = con.execute("select status, space_size from conjecture where slug='totient-even'").fetchone()
    assert row == ("VERIFIED_EXHAUSTIVE", 100)
    assert con.execute("select count(*) from counterexample").fetchone()[0] == 0
    assert con.execute("select count(*) from falsification").fetchone()[0] == 0
    con.close()
