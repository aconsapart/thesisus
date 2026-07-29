from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st


def get_db_path() -> str:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--db", default="proof_codex.sqlite")
    args, _ = parser.parse_known_args()
    return args.db


DB_PATH = get_db_path()


@st.cache_data(ttl=3)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    if not Path(DB_PATH).exists():
        return pd.DataFrame()
    con = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()


st.set_page_config(page_title="Math Proof Codex", layout="wide")
st.title("Math Proof Codex")
st.caption(f"Database: {DB_PATH}")

tabs = st.tabs([
    "Frontier",
    "Theorems",
    "Conjectures",
    "Counterexamples",
    "Prior art",
    "Strategies",
    "Attempts",
    "Falsifications",
    "Computations",
    "Formalization",
    "SQL",
])

with tabs[0]:
    st.header("Current frontier")

    # Both tracks at a glance. A run that only ever proves things and a run that
    # never finds a counterexample look identical without this row.
    proved = query("select count(*) as n from theorem where status='PROVED'")
    falsified = query("select count(*) as n from theorem where status='FALSIFIED'")
    witnesses = query("select count(*) as n from counterexample where verification='VERIFIED_EXACT'")
    contested = query("select count(*) as n from counterexample where verification='CONTESTED'")
    discarded = query("select count(*) as n from counterexample where verification='REJECTED'")

    def scalar(df, default=0):
        return int(df["n"].iloc[0]) if not df.empty else default

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Proved", scalar(proved))
    c2.metric("Falsified", scalar(falsified))
    c3.metric("Verified witnesses", scalar(witnesses))
    c4.metric("Claims discarded", scalar(discarded), help="Proposed witnesses that failed independent checking.")
    c5.metric("Contested", scalar(contested), help="Evaluators disagreed. This is a bug to investigate, not a result.")

    if scalar(contested):
        st.error(
            f"{scalar(contested)} witness(es) are CONTESTED: the rational and symbolic evaluators "
            "disagree about them. One of the two is wrong. No refutation should be trusted until "
            "this is resolved -- see the Counterexamples tab."
        )

    st.dataframe(query("""
        select p.title as problem, t.slug, t.title, t.status, t.frontier_rank, t.updated_at
        from theorem t join problem p on p.id=t.problem_id
        order by t.frontier_rank asc nulls last, t.updated_at desc
        limit 50
    """), use_container_width=True)
    st.subheader("Problems")
    st.dataframe(query("select id, slug, title, domain, updated_at from problem order by updated_at desc"), use_container_width=True)

with tabs[1]:
    st.header("Theorem ledger")
    status = st.selectbox("Status", ["ALL", "PROVED", "CONDITIONAL", "COMPUTATIONAL", "HEURISTIC", "FAILED/OPEN", "FALSIFIED"])
    if status == "ALL":
        df = query("""
            select t.id, p.slug as problem, t.slug, t.title, t.status, t.frontier_rank, t.updated_at
            from theorem t join problem p on p.id=t.problem_id
            order by t.updated_at desc
        """)
    else:
        df = query("""
            select t.id, p.slug as problem, t.slug, t.title, t.status, t.frontier_rank, t.updated_at
            from theorem t join problem p on p.id=t.problem_id
            where t.status=?
            order by t.updated_at desc
        """, (status,))
    st.dataframe(df, use_container_width=True)

with tabs[2]:
    st.header("Conjectures")
    st.caption(
        "Machine-checkable claims declared in the problem spec. FALSIFIED means a witness "
        "was found and independently checked. VERIFIED_EXHAUSTIVE means no witness exists "
        "anywhere in the declared space -- a proof over that space only. OPEN means the "
        "search settled nothing."
    )
    st.dataframe(query("select * from v_conjecture_board"), use_container_width=True)
    st.subheader("Full specifications")
    st.dataframe(query("""
        select cj.slug, cj.status, cj.statement_md, cj.predicate, cj.variables_json,
               cj.assumptions_json, cj.space_size, cj.updated_at
        from conjecture cj order by cj.updated_at desc
    """), use_container_width=True)

with tabs[3]:
    st.header("Counterexamples")

    contested_df = query("select * from v_contested_counterexamples")
    if not contested_df.empty:
        st.error(
            "The two independent evaluators disagreed about the witnesses below. "
            "One of them has a bug. Nothing here is evidence until that is resolved."
        )
        st.dataframe(contested_df, use_container_width=True)

    st.subheader("Verified")
    st.caption(
        "VERIFIED_EXACT: the rational and the symbolic evaluator independently agree the "
        "predicate fails at this assignment. VERIFIED_SINGLE: only one evaluator could "
        "decide it, so it is weaker evidence."
    )
    st.dataframe(query("select * from v_verified_counterexamples"), use_container_width=True)

    st.subheader("Discarded claims")
    st.caption(
        "Witnesses that were proposed and did not survive checking. Kept deliberately: "
        "a lane that keeps proposing the same dead assignment is a lane worth demoting."
    )
    st.dataframe(query("""
        select c.id, cj.slug as conjecture, c.witness_md, c.source, c.verifier_notes_md,
               c.rationale_md, c.iteration, c.created_at
        from counterexample c
        left join conjecture cj on cj.id=c.conjecture_id
        where c.verification in ('REJECTED','UNCHECKED')
        order by c.created_at desc
        limit 200
    """), use_container_width=True)

with tabs[4]:
    st.header("Prior art")
    st.caption(
        "The third way a claim can die: not false, not unproved, just already "
        "published. KILLED means the literature already reports it. WOUNDED means "
        "it must be narrowed to survive a citation. UNDER_SEARCHED means nothing "
        "was found but the search does not yet support saying so."
    )

    board = query("select * from v_claim_board")
    if board.empty:
        st.info(
            "No claims declared. Add a `claims:` block to the problem YAML listing each "
            "separately attackable contribution. Nothing here says the work is novel — "
            "only that novelty was never checked."
        )
    else:
        blocked = int((board["status"].isin(["KILLED", "WOUNDED"])).sum())
        unsearched = int((board["status"] == "UNDER_SEARCHED").sum())
        b1, b2, b3 = st.columns(3)
        b1.metric("Clear", int((board["status"] == "CLEAR").sum()))
        b2.metric("Killed or wounded", blocked, help="Cannot be stated as written.")
        b3.metric(
            "Under-searched",
            unsearched,
            help="Nothing found, but the search has not earned a clear verdict.",
        )
        if unsearched:
            st.warning(
                f"{unsearched} claim(s) are UNDER_SEARCHED. Finding a killer is evidence "
                "however you looked; finding nothing is evidence only if you looked "
                "properly — at least two independent passes, all four angles, and logged "
                "negative searches."
            )
        st.dataframe(board, use_container_width=True)

    st.subheader("Threats to cite and distinguish")
    st.dataframe(query("select * from v_prior_art_threats"), use_container_width=True)

    st.subheader("Negative searches")
    st.caption(
        "Queries that returned nothing. These are the evidence behind every CLEAR "
        "verdict; a clear claim with no rows here is unsupported."
    )
    st.dataframe(query("select * from v_negative_searches"), use_container_width=True)

    st.subheader("Full search log")
    st.dataframe(query("""
        select ps.slug as search_pass, ps.phrasing, ps.engine, q.angle, q.query_text,
               q.results, q.notes_md, q.created_at
        from prior_art_query q
        left join prior_art_pass ps on ps.id = q.pass_id
        order by q.created_at desc
        limit 300
    """), use_container_width=True)

with tabs[5]:
    st.header("Strategies")
    st.dataframe(query("select id, slug, name, rank, status, score, updated_at from strategy order by rank, score desc"), use_container_width=True)

with tabs[6]:
    st.header("Attempts")
    st.dataframe(query("""
        select a.id, p.slug as problem, s.slug as strategy, a.iteration, a.status, a.created_at,
               substr(a.result_md,1,500) as result_preview
        from attempt a
        left join problem p on p.id=a.problem_id
        left join strategy s on s.id=a.strategy_id
        order by a.created_at desc
        limit 200
    """), use_container_width=True)

with tabs[7]:
    st.header("Falsifications")
    st.dataframe(query("""
        select f.id, p.slug as problem, s.slug as strategy, f.severity, f.created_at,
               f.obstruction_md, f.counterexample_md
        from falsification f
        left join problem p on p.id=f.problem_id
        left join strategy s on s.id=f.strategy_id
        order by f.created_at desc
    """), use_container_width=True)

with tabs[8]:
    st.header("Computations")
    st.dataframe(query("""
        select c.id, p.slug as problem, c.iteration, c.name, c.status, c.code_path, c.data_path, c.report_path, c.created_at
        from computation c
        left join problem p on p.id=c.problem_id
        order by c.created_at desc
        limit 200
    """), use_container_width=True)

with tabs[9]:
    st.header("Formalization")
    st.dataframe(query("""
        select f.id, p.slug as problem, f.backend, f.status, f.lean_path, f.updated_at
        from formalization_job f
        left join problem p on p.id=f.problem_id
        order by f.updated_at desc
    """), use_container_width=True)

with tabs[10]:
    st.header("SQL")
    sql = st.text_area("Query", "select * from theorem limit 20", height=160)
    if st.button("Run query"):
        st.dataframe(query(sql), use_container_width=True)
