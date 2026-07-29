from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from math_workbench.tools.migrate import MigrationReport, migrate

# FALSIFIED is a first-class outcome: a claim killed by a checked counterexample
# is as settled as one that was proved, and the ledger must be able to say so.
VALID_STATUSES = {"PROVED", "CONDITIONAL", "COMPUTATIONAL", "HEURISTIC", "FAILED/OPEN", "FALSIFIED"}

VALID_CONJECTURE_STATUSES = {"OPEN", "FALSIFIED", "VERIFIED_EXHAUSTIVE", "CONTESTED", "PROVED"}
VALID_VERIFICATIONS = {"VERIFIED_EXACT", "VERIFIED_SINGLE", "CONTESTED", "REJECTED", "UNCHECKED"}
VALID_SOURCES = {"AUTO_SEARCH", "LLM_LANE", "MANUAL", "CAS"}
VALID_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "KILLS_STRATEGY"}


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.execute("pragma journal_mode=wal;")
    con.execute("pragma foreign_keys=on;")
    return con


def init_db(db_path: str, schema_path: str | None = None) -> MigrationReport:
    """Create the codex and upgrade a pre-counterexample database in place."""
    con = connect(db_path)
    if schema_path is None:
        schema_path = str(Path(__file__).resolve().parents[3] / "data" / "schema.sql")
    con.executescript(Path(schema_path).read_text(encoding="utf-8"))
    con.commit()
    report = migrate(con)
    con.commit()
    con.close()
    return report


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


# --------------------------------------------------------------------------
# Refutation ledger.
#
# The schema has always had a `falsification` table, but before this refactor
# nothing wrote to it: the dashboard's "Falsifications" tab could only ever be
# empty. These are the writers that make refutation a recorded outcome rather
# than a line in a prompt.
# --------------------------------------------------------------------------


def _canonical_witness(assignment: dict[str, Any]) -> str:
    """Stable JSON so the same witness found twice collapses to one row."""
    return json.dumps(assignment, sort_keys=True, default=str)


def upsert_conjecture(con: sqlite3.Connection, problem_id: int, conjecture: Any) -> int:
    """Persist a conjecture. Accepts a `Conjecture` object or a plain dict."""
    get = (lambda k, d=None: getattr(conjecture, k, d)) if not isinstance(conjecture, dict) else conjecture.get
    slug = str(get("id") or get("slug") or "conjecture")
    variables = get("variables") or {}
    variables_json = json.dumps(
        {name: (dom.describe() if hasattr(dom, "describe") else str(dom)) for name, dom in variables.items()}
        if isinstance(variables, dict)
        else str(variables)
    )
    space_size = None
    if hasattr(conjecture, "space_size"):
        try:
            space_size = int(conjecture.space_size())
        except Exception:  # pragma: no cover - defensive: a bad domain must not block logging
            space_size = None
    cur = con.execute(
        """
        insert into conjecture(problem_id,slug,statement_md,quantifier,predicate,variables_json,
                               assumptions_json,targets_json,space_size,notes_md)
        values (?,?,?,?,?,?,?,?,?,?)
        on conflict(problem_id,slug) do update set
            statement_md=excluded.statement_md,
            quantifier=excluded.quantifier,
            predicate=excluded.predicate,
            variables_json=excluded.variables_json,
            assumptions_json=excluded.assumptions_json,
            targets_json=excluded.targets_json,
            space_size=excluded.space_size,
            notes_md=excluded.notes_md,
            updated_at=current_timestamp
        returning id
        """,
        (
            problem_id,
            slug,
            str(get("statement", slug)),
            str(get("quantifier", "FORALL")),
            str(get("predicate", "")),
            variables_json,
            json.dumps(list(get("assumptions") or [])),
            json.dumps(list(get("targets") or [])),
            space_size,
            str(get("notes", "")),
        ),
    )
    cjid = int(cur.fetchone()[0])
    con.commit()
    return cjid


def set_conjecture_status(con: sqlite3.Connection, conjecture_id: int, status: str, notes: str | None = None) -> None:
    if status not in VALID_CONJECTURE_STATUSES:
        raise ValueError(f"unknown conjecture status {status!r}; expected one of {sorted(VALID_CONJECTURE_STATUSES)}")
    con.execute(
        "update conjecture set status=?, notes_md=coalesce(?, notes_md), updated_at=current_timestamp where id=?",
        (status, notes, conjecture_id),
    )
    con.commit()


def insert_falsification(
    con: sqlite3.Connection,
    problem_id: int,
    obstruction: str,
    *,
    counterexample_md: str | None = None,
    severity: str = "MEDIUM",
    theorem_id: int | None = None,
    strategy_id: int | None = None,
    run_id: str | None = None,
    iteration: int | None = None,
) -> int:
    """Record an obstruction: something that blocks a route, with or without a witness."""
    if severity not in VALID_SEVERITIES:
        severity = "MEDIUM"
    cur = con.execute(
        """
        insert into falsification(problem_id,theorem_id,strategy_id,run_id,iteration,
                                  obstruction_md,counterexample_md,severity)
        values (?,?,?,?,?,?,?,?) returning id
        """,
        (problem_id, theorem_id, strategy_id, run_id, iteration, obstruction, counterexample_md, severity),
    )
    fid = int(cur.fetchone()[0])
    con.commit()
    return fid


def insert_counterexample(
    con: sqlite3.Connection,
    problem_id: int,
    conjecture_id: int | None,
    witness: Any,
    *,
    run_id: str | None = None,
    iteration: int | None = None,
    theorem_id: int | None = None,
    strategy_id: int | None = None,
    falsification_id: int | None = None,
) -> int:
    """Store one checked witness.

    `witness` is a `refutation.Witness` (or any object exposing the same
    fields). The verification verdict is stored verbatim -- callers must not
    launder a `CONTESTED` or `REJECTED` witness into a refutation.
    """
    get = (lambda k, d=None: getattr(witness, k, d)) if not isinstance(witness, dict) else witness.get
    verification = str(get("verification", "UNCHECKED"))
    if verification not in VALID_VERIFICATIONS:
        raise ValueError(f"unknown verification {verification!r}; expected one of {sorted(VALID_VERIFICATIONS)}")
    source = str(get("source", "AUTO_SEARCH"))
    if source not in VALID_SOURCES:
        source = "MANUAL"
    assignment = get("assignment") or {}
    witness_json = _canonical_witness({k: str(v) for k, v in assignment.items()})
    witness_md = ", ".join(f"{k} = {v}" for k, v in sorted(assignment.items())) or "(empty assignment)"
    cur = con.execute(
        """
        insert into counterexample(problem_id,conjecture_id,theorem_id,strategy_id,falsification_id,
                                   run_id,iteration,source,witness_json,witness_md,verification,
                                   verifier_notes_md,rationale_md,minimal)
        values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        on conflict(conjecture_id,witness_json) do update set
            verification=excluded.verification,
            verifier_notes_md=excluded.verifier_notes_md,
            minimal=max(counterexample.minimal, excluded.minimal)
        returning id
        """,
        (
            problem_id,
            conjecture_id,
            theorem_id,
            strategy_id,
            falsification_id,
            run_id,
            iteration,
            source,
            witness_json,
            witness_md,
            verification,
            str(get("detail", "")),
            str(get("rationale", "")),
            1 if get("minimal", False) else 0,
        ),
    )
    xid = int(cur.fetchone()[0])
    con.commit()
    return xid


def record_search_outcome(
    con: sqlite3.Connection,
    problem_id: int,
    conjecture: Any,
    outcome: Any,
    *,
    run_id: str | None = None,
    iteration: int | None = None,
    strategy_id: int | None = None,
) -> dict[str, Any]:
    """Persist a whole search: the conjecture, its status, and every witness.

    Returns the ids written, so a caller can link a theorem to the witness that
    killed it.
    """
    conjecture_id = upsert_conjecture(con, problem_id, conjecture)
    status = str(getattr(outcome, "status", "OPEN"))
    notes = str(getattr(outcome, "notes", "")) or None
    set_conjecture_status(con, conjecture_id, status, notes)

    written: list[int] = []
    witnesses = list(getattr(outcome, "witnesses", [])) + list(getattr(outcome, "contested", []))
    for witness in witnesses:
        written.append(
            insert_counterexample(
                con,
                problem_id,
                conjecture_id,
                witness,
                run_id=run_id,
                iteration=iteration,
                strategy_id=strategy_id,
            )
        )

    falsification_id = None
    verified = [w for w in getattr(outcome, "witnesses", []) if getattr(w, "refutes", lambda: False)()]
    if verified:
        first = verified[0]
        falsification_id = insert_falsification(
            con,
            problem_id,
            obstruction=f"Conjecture {getattr(conjecture, 'id', '?')} is false: "
            f"{getattr(outcome, 'statement', '')}",
            counterexample_md=first.describe() if hasattr(first, "describe") else str(first),
            severity="KILLS_STRATEGY" if any(w.verification == "VERIFIED_EXACT" for w in verified) else "HIGH",
            strategy_id=strategy_id,
            run_id=run_id,
            iteration=iteration,
        )
    return {
        "conjecture_id": conjecture_id,
        "counterexample_ids": written,
        "falsification_id": falsification_id,
        "status": status,
    }


# --------------------------------------------------------------------------
# Prior-art ledger.
#
# The third way a claim dies: not false, not unproved, just already published.
# Kept alongside the other two so the claims board and the conjecture board sit
# in the same database and can be read together.
# --------------------------------------------------------------------------

VALID_CLAIM_STATUSES = {"KILLED", "WOUNDED", "CLEAR", "UNDER_SEARCHED"}
VALID_THREAT_VERDICTS = {"KILLS", "WOUNDS", "ADJACENT", "BACKGROUND"}


def upsert_claim(con: sqlite3.Connection, problem_id: int, claim: Any) -> int:
    """Persist a declared claim before anything has been searched for it."""
    get = (lambda k, d=None: getattr(claim, k, d)) if not isinstance(claim, dict) else claim.get
    slug = str(get("id") or get("slug") or "claim")
    cur = con.execute(
        """
        insert into claim_contribution(problem_id,slug,statement_md,kind,novelty_basis_md)
        values (?,?,?,?,?)
        on conflict(problem_id,slug) do update set
            statement_md=excluded.statement_md,
            kind=excluded.kind,
            novelty_basis_md=excluded.novelty_basis_md,
            updated_at=current_timestamp
        returning id
        """,
        (
            problem_id,
            slug,
            str(get("statement", slug)),
            str(get("kind", "CONTRIBUTION")),
            str(get("novelty_basis", "")),
        ),
    )
    cid = int(cur.fetchone()[0])
    con.commit()
    return cid


def insert_search_pass(
    con: sqlite3.Connection,
    problem_id: int,
    search_pass: Any,
    *,
    run_id: str | None = None,
    iteration: int | None = None,
) -> int:
    """Record one sweep and its full query log, negatives included."""
    get = (lambda k, d=None: getattr(search_pass, k, d)) if not isinstance(search_pass, dict) else search_pass.get
    slug = str(get("id") or "pass")
    cur = con.execute(
        """
        insert into prior_art_pass(problem_id,run_id,iteration,slug,phrasing,engine,notes_md)
        values (?,?,?,?,?,?,?)
        on conflict(problem_id,run_id,slug) do update set
            phrasing=excluded.phrasing,
            engine=excluded.engine,
            notes_md=excluded.notes_md
        returning id
        """,
        (
            problem_id,
            run_id,
            iteration,
            slug,
            str(get("phrasing", "")),
            str(get("engine", "")),
            str(get("notes", "")),
        ),
    )
    pass_id = int(cur.fetchone()[0])
    con.execute("delete from prior_art_query where pass_id=?", (pass_id,))
    for query in get("queries", []) or []:
        qget = (lambda k, d=None: getattr(query, k, d)) if not isinstance(query, dict) else query.get
        con.execute(
            """
            insert into prior_art_query(pass_id,problem_id,query_text,angle,engine,results,notes_md)
            values (?,?,?,?,?,?,?)
            """,
            (
                pass_id,
                problem_id,
                str(qget("text", "")),
                str(qget("angle", "")),
                str(qget("engine", "")),
                int(qget("results", 0) or 0),
                str(qget("notes", "")),
            ),
        )
    con.commit()
    return pass_id


def insert_threat(
    con: sqlite3.Connection,
    problem_id: int,
    claim_id: int | None,
    threat: Any,
    *,
    pass_id: int | None = None,
) -> int:
    get = (lambda k, d=None: getattr(threat, k, d)) if not isinstance(threat, dict) else threat.get
    verdict = str(get("verdict", "BACKGROUND")).upper()
    if verdict not in VALID_THREAT_VERDICTS:
        raise ValueError(f"unknown threat verdict {verdict!r}; expected one of {sorted(VALID_THREAT_VERDICTS)}")
    cur = con.execute(
        """
        insert into prior_art_threat(problem_id,claim_id,pass_id,verdict,source,locator,angle,evidence_md)
        values (?,?,?,?,?,?,?,?)
        on conflict(claim_id,source,locator) do update set
            verdict=excluded.verdict,
            angle=excluded.angle,
            evidence_md=excluded.evidence_md
        returning id
        """,
        (
            problem_id,
            claim_id,
            pass_id,
            verdict,
            str(get("source", "")),
            str(get("locator", "")),
            str(get("angle", "")),
            str(get("evidence", "")),
        ),
    )
    tid = int(cur.fetchone()[0])
    con.commit()
    return tid


def record_claim_assessment(
    con: sqlite3.Connection,
    problem_id: int,
    assessment: Any,
    *,
    pass_ids: dict[str, int] | None = None,
) -> int:
    """Persist a claim's verdict and every threat aimed at it."""
    get = (lambda k, d=None: getattr(assessment, k, d)) if not isinstance(assessment, dict) else assessment.get
    status = str(get("status", "UNDER_SEARCHED"))
    if status not in VALID_CLAIM_STATUSES:
        raise ValueError(f"unknown claim status {status!r}; expected one of {sorted(VALID_CLAIM_STATUSES)}")

    slug = str(get("claim_id", "claim"))
    claim_id = upsert_claim(
        con, problem_id, {"id": slug, "statement": str(get("statement", slug))}
    )
    # `unearned_overclaims` is a method on ClaimAssessment and a plain list in
    # the dict form, so handle both rather than silently storing nothing.
    raw_overclaims = get("unearned_overclaims", []) or []
    if callable(raw_overclaims):
        raw_overclaims = raw_overclaims()
    overclaims = [str(o) for o in raw_overclaims]
    con.execute(
        """
        update claim_contribution set
            status=?,
            passes_searched=?,
            angles_covered_json=?,
            missing_angles_json=?,
            negative_queries=?,
            reasons_md=?,
            overclaims_json=?,
            surgery_required=?,
            updated_at=current_timestamp
        where id=?
        """,
        (
            status,
            int(get("passes_searched", 0) or 0),
            json.dumps(sorted(get("angles_covered", set()) or [])),
            json.dumps(sorted(get("missing_angles", set()) or [])),
            int(get("negative_queries", 0) or 0),
            "\n".join(get("reasons", []) or []),
            json.dumps(overclaims),
            1 if get("surgery_required", False) else 0,
            claim_id,
        ),
    )
    for threat in get("threats", []) or []:
        tget = (lambda k, d=None: getattr(threat, k, d)) if not isinstance(threat, dict) else threat.get
        insert_threat(
            con,
            problem_id,
            claim_id,
            threat,
            pass_id=(pass_ids or {}).get(str(tget("pass_id", ""))),
        )
    con.commit()
    return claim_id


def claims_blocking_publication(con: sqlite3.Connection, problem_id: int | None = None) -> list[dict[str, Any]]:
    """Claims that cannot be stated as written, newest first."""
    sql = (
        "select slug, status, statement_md, reasons_md, surgery_required "
        "from claim_contribution where status in ('KILLED','WOUNDED') or surgery_required=1"
    )
    params: tuple[Any, ...] = ()
    if problem_id is not None:
        sql += " and problem_id=?"
        params = (problem_id,)
    sql += " order by updated_at desc"
    cur = con.execute(sql, params)
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def verified_counterexamples(con: sqlite3.Connection, problem_id: int | None = None) -> list[dict[str, Any]]:
    """Witnesses that survived independent checking, newest first."""
    sql = "select * from v_verified_counterexamples"
    params: tuple[Any, ...] = ()
    if problem_id is not None:
        sql = (
            "select c.id, c.witness_md, c.verification, c.source, c.minimal, c.iteration, c.created_at, "
            "cj.slug as conjecture from counterexample c "
            "left join conjecture cj on cj.id=c.conjecture_id "
            "where c.problem_id=? and c.verification in ('VERIFIED_EXACT','VERIFIED_SINGLE') "
            "order by c.created_at desc"
        )
        params = (problem_id,)
    cur = con.execute(sql, params)
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]
