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

tabs = st.tabs(["Frontier", "Theorems", "Strategies", "Attempts", "Falsifications", "Computations", "Formalization", "SQL"])

with tabs[0]:
    st.header("Current frontier")
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
    status = st.selectbox("Status", ["ALL", "PROVED", "CONDITIONAL", "COMPUTATIONAL", "HEURISTIC", "FAILED/OPEN"])
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
    st.header("Strategies")
    st.dataframe(query("select id, slug, name, rank, status, score, updated_at from strategy order by rank, score desc"), use_container_width=True)

with tabs[3]:
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

with tabs[4]:
    st.header("Falsifications")
    st.dataframe(query("""
        select f.id, p.slug as problem, s.slug as strategy, f.severity, f.created_at,
               f.obstruction_md, f.counterexample_md
        from falsification f
        left join problem p on p.id=f.problem_id
        left join strategy s on s.id=f.strategy_id
        order by f.created_at desc
    """), use_container_width=True)

with tabs[5]:
    st.header("Computations")
    st.dataframe(query("""
        select c.id, p.slug as problem, c.iteration, c.name, c.status, c.code_path, c.data_path, c.report_path, c.created_at
        from computation c
        left join problem p on p.id=c.problem_id
        order by c.created_at desc
        limit 200
    """), use_container_width=True)

with tabs[6]:
    st.header("Formalization")
    st.dataframe(query("""
        select f.id, p.slug as problem, f.backend, f.status, f.lean_path, f.updated_at
        from formalization_job f
        left join problem p on p.id=f.problem_id
        order by f.updated_at desc
    """), use_container_width=True)

with tabs[7]:
    st.header("SQL")
    sql = st.text_area("Query", "select * from theorem limit 20", height=160)
    if st.button("Run query"):
        st.dataframe(query(sql), use_container_width=True)
