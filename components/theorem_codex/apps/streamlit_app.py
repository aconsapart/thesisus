"""Theorem Codex dashboard: proven results only.

A read-only view of the codex: a status dashboard, the proven theorems, their
proofs, and the peer-review scores produced by the paper pipeline. Task
prompting was removed — proof work is driven by the agents and scored by
`thesius paper review`, so the dashboard only reports.
"""

from __future__ import annotations

import argparse
import hmac
import html
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from theorem_codex.db import init_db  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--db", default=str(ROOT / "proof_codex.sqlite"))
    args, _ = parser.parse_known_args()
    return args


ARGS = parse_args()
DB_PATH = Path(ARGS.db)

st.set_page_config(page_title="Theorem Codex", layout="wide", initial_sidebar_state="collapsed")


def install_css() -> None:
    st.markdown(
        """
<style>
div[data-testid="stSidebar"] {
  display: none;
}
.main .block-container {
  padding: 0.65rem 1rem 1rem;
  max-width: 60rem;
}
h1, h2, h3 {
  letter-spacing: 0;
}
.atlas-shell {
  border-bottom: 1px solid #ececec;
  padding: 0.1rem 0 0.55rem;
  margin-bottom: 0.6rem;
}
.atlas-title {
  font-size: 0.95rem;
  font-weight: 650;
}
.atlas-subtitle {
  color: #666;
  font-size: 0.78rem;
}
.status-pill {
  border: 1px solid #dadada;
  border-radius: 999px;
  display: inline-block;
  font-size: 0.72rem;
  padding: 0.1rem 0.5rem;
  color: #555;
  background: #fff;
}
.review-pill {
  border: 1px solid #cfe3cf;
  border-radius: 999px;
  display: inline-block;
  font-size: 0.72rem;
  padding: 0.1rem 0.5rem;
  color: #23662a;
  background: #f2faf2;
}
.metric-grid {
  border: 1px solid #ececec;
  border-radius: 8px;
  background: #fff;
  color: #555;
  display: flex;
  flex-wrap: wrap;
  font-size: 0.74rem;
  gap: 0.55rem 0.75rem;
  line-height: 1.3;
  margin: 0.55rem 0 0.75rem;
  padding: 0.55rem 0.65rem;
}
.metric-grid strong {
  color: #111;
  font-size: 0.82rem;
  margin-right: 0.15rem;
}
.proof-card {
  border: 1px solid #e9e9e9;
  border-radius: 8px;
  padding: 0.62rem 0.7rem;
  margin: 0.35rem 0;
  background: white;
}
.proof-title {
  font-size: 0.85rem;
  font-weight: 650;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
.proof-meta {
  color: #777;
  font-size: 0.72rem;
  margin-top: 0.18rem;
}
.small-note {
  color: #777;
  font-size: 0.76rem;
}
</style>
""",
        unsafe_allow_html=True,
    )


def oidc_enabled() -> bool:
    try:
        return bool(st.secrets["auth"].get("client_id"))
    except Exception:
        return False


def allowed_emails() -> set[str] | None:
    raw = os.environ.get("THESIUS_ALLOWED_EMAILS", "")
    if not raw:
        try:
            value = st.secrets.get("thesius_allowed_emails", "")
            raw = ",".join(value) if isinstance(value, (list, tuple)) else str(value or "")
        except Exception:
            raw = ""
    emails = {email.strip().lower() for email in raw.split(",") if email.strip()}
    return emails or None


def current_user_email() -> str:
    try:
        return str(getattr(st.user, "email", "") or "").lower()
    except Exception:
        return ""


def user_logged_in() -> bool:
    try:
        return bool(st.user.is_logged_in)
    except Exception:
        return False


def require_oidc_login() -> None:
    if not user_logged_in():
        _, center_col, _ = st.columns([0.35, 0.3, 0.35])
        with center_col:
            st.markdown('<div class="atlas-title">Theorem Codex</div><div class="atlas-subtitle">Sign in to continue</div>', unsafe_allow_html=True)
            st.button("Sign in", width="stretch", on_click=st.login)
        st.stop()
    allowed = allowed_emails()
    if allowed is not None and current_user_email() not in allowed:
        _, center_col, _ = st.columns([0.35, 0.3, 0.35])
        with center_col:
            st.markdown('<div class="atlas-title">Theorem Codex</div>', unsafe_allow_html=True)
            st.error(f"{current_user_email() or 'This account'} is not authorized for this codex.")
            st.button("Sign out", width="stretch", on_click=st.logout)
        st.stop()


def expected_password() -> str:
    password = os.environ.get("THESIUS_PASSWORD", "")
    if password:
        return password
    try:
        return str(st.secrets.get("thesius_password", ""))
    except Exception:
        return ""


def auth_enabled() -> bool:
    return bool(expected_password())


def _check_login() -> None:
    password = str(st.session_state.get("login_password", ""))
    st.session_state["login_password"] = ""
    if hmac.compare_digest(password, expected_password()):
        st.session_state["authenticated"] = True
        st.session_state["login_error"] = False
    else:
        st.session_state["authenticated"] = False
        st.session_state["login_error"] = True


def require_login() -> None:
    if oidc_enabled():
        require_oidc_login()
        return
    if not auth_enabled() or st.session_state.get("authenticated"):
        return
    _, center_col, _ = st.columns([0.35, 0.3, 0.35])
    with center_col:
        st.markdown('<div class="atlas-title">Theorem Codex</div><div class="atlas-subtitle">Sign in to continue</div>', unsafe_allow_html=True)
        with st.form("login_form"):
            st.text_input("Password", type="password", key="login_password")
            st.form_submit_button("Sign in", width="stretch", on_click=_check_login)
        if st.session_state.get("login_error"):
            st.error("Incorrect password.")
    st.stop()


def ensure_db() -> None:
    if not DB_PATH.exists():
        init_db(DB_PATH)


@st.cache_data(ttl=2)
def _q(db_path: str, sql: str, params: tuple[Any, ...]) -> pd.DataFrame:
    ensure_db()
    con = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()
    # Normalize SQL NULLs to None: newer pandas surfaces them as truthy NaN
    # in mixed columns, which would defeat `or`/`if` guards and render "nan".
    return df.astype(object).where(df.notna(), None)


def q(sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    # The DB path is part of the cache key so switching databases (or tests
    # running against different temp DBs) can never serve stale results.
    return _q(str(DB_PATH), sql, params)


def h(text: Any) -> str:
    return html.escape("" if text is None else str(text))


def val(x: Any) -> Any:
    """Normalize a scalar from pandas: SQL NULLs may surface as None, NaN,
    or pd.NA depending on dtype and cache round-trips — map them all to None."""
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        pass
    return x


# --- Data access (read-only, proven results) --------------------------------


def status_counts() -> pd.DataFrame:
    return q("SELECT status, count(*) count FROM theorem GROUP BY status ORDER BY count DESC")


def proven_theorems(search: str = "") -> pd.DataFrame:
    """Proven theorems, optionally filtered by a search over their proofs.

    The search matches the theorem title/statement and the text of its
    PROVED attempts and claims — nothing else.
    """
    base = """
        SELECT t.*,
               (SELECT count(*) FROM attempt a
                WHERE a.theorem_id=t.id AND a.status='PROVED') proved_attempts,
               (SELECT count(*) FROM claim c
                WHERE c.theorem_id=t.id AND c.status='PROVED') proved_claims
        FROM theorem t
        WHERE t.status='PROVED'
    """
    if not search:
        return q(base + " ORDER BY t.updated_at DESC")
    # Escape LIKE wildcards: proof text is LaTeX-heavy, so literal
    # underscores in a search must not act as single-character wildcards.
    escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like = f"%{escaped}%"
    return q(
        base
        + """
          AND (
                t.slug LIKE ? ESCAPE '\\' OR t.title LIKE ? ESCAPE '\\'
             OR t.statement_md LIKE ? ESCAPE '\\'
             OR EXISTS (SELECT 1 FROM attempt a WHERE a.theorem_id=t.id
                        AND a.status='PROVED'
                        AND (a.result_md LIKE ? ESCAPE '\\' OR a.title LIKE ? ESCAPE '\\'))
             OR EXISTS (SELECT 1 FROM claim c WHERE c.theorem_id=t.id
                        AND c.status='PROVED'
                        AND (c.claim_md LIKE ? ESCAPE '\\' OR c.proof_sketch_md LIKE ? ESCAPE '\\'))
          )
          ORDER BY t.updated_at DESC
        """,
        (like, like, like, like, like, like, like),
    )


def proofs_for(theorem_id: int) -> pd.DataFrame:
    return q(
        """
        SELECT a.created_at, a.title, a.result_md, a.model, s.slug strategy
        FROM attempt a
        LEFT JOIN strategy s ON s.id=a.strategy_id
        WHERE a.theorem_id=? AND a.status='PROVED'
        ORDER BY a.created_at DESC
        """,
        (theorem_id,),
    )


def proved_claims_for(theorem_id: int) -> pd.DataFrame:
    return q(
        """
        SELECT created_at, claim_md, proof_sketch_md
        FROM claim
        WHERE theorem_id=? AND status='PROVED'
        ORDER BY created_at DESC
        """,
        (theorem_id,),
    )


def latest_artifact(theorem_id: int, kind: str) -> pd.Series | None:
    df = q(
        "SELECT path, description_md, created_at FROM artifact "
        "WHERE theorem_id=? AND kind=? ORDER BY created_at DESC, id DESC LIMIT 1",
        (theorem_id, kind),
    )
    if df.empty:
        return None
    return df.iloc[0]


def load_review_score(theorem_id: int) -> dict[str, Any] | None:
    """Latest peer-review score for a theorem's paper, if one was recorded."""
    artifact = latest_artifact(theorem_id, "paper_review")
    if artifact is None:
        return None
    path = Path(str(artifact["path"]))
    if not path.is_file() and not path.is_absolute():
        # Artifact paths are stored as given to the CLI; try them relative
        # to the database directory as well.
        candidate = DB_PATH.parent / path
        if candidate.is_file():
            path = candidate
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        # ValueError covers both JSONDecodeError and UnicodeDecodeError.
        return None
    if not isinstance(data, dict):
        return None
    review = data.get("review")
    if not isinstance(review, dict):
        return None
    return {
        "overall": review.get("Overall"),
        "decision": review.get("Decision"),
        "soundness": review.get("Soundness"),
        "summary": review.get("Summary"),
        "reviewed_at": artifact["created_at"],
    }


def dashboard_metrics() -> dict[str, Any]:
    proven = int(q("SELECT count(*) count FROM theorem WHERE status='PROVED'").iloc[0]["count"])
    proofs = int(
        q(
            "SELECT (SELECT count(*) FROM attempt a JOIN theorem t ON t.id=a.theorem_id "
            " WHERE a.status='PROVED' AND t.status='PROVED') + "
            "(SELECT count(*) FROM claim c JOIN theorem t ON t.id=c.theorem_id "
            " WHERE c.status='PROVED' AND t.status='PROVED') count"
        ).iloc[0]["count"]
    )
    reviewed = int(
        q(
            "SELECT count(DISTINCT a.theorem_id) count FROM artifact a "
            "JOIN theorem t ON t.id=a.theorem_id "
            "WHERE a.kind='paper_review' AND t.status='PROVED'"
        ).iloc[0]["count"]
    )
    return {"proven": proven, "proofs": proofs, "reviewed": reviewed}


# --- Rendering ---------------------------------------------------------------


def render_header() -> None:
    st.markdown(
        '<div class="atlas-shell"><div class="atlas-title">Theorem Codex</div>'
        '<div class="atlas-subtitle">Proven results</div></div>',
        unsafe_allow_html=True,
    )


def render_status_dashboard() -> None:
    metrics = dashboard_metrics()
    st.markdown(
        f"""
<div class="metric-grid">
  <span><strong>{metrics["proven"]}</strong>proven theorems</span>
  <span><strong>{metrics["proofs"]}</strong>proofs on record</span>
  <span><strong>{metrics["reviewed"]}</strong>peer-reviewed</span>
</div>
""",
        unsafe_allow_html=True,
    )
    counts = status_counts()
    if not counts.empty:
        with st.expander("Codex status breakdown", expanded=False):
            st.dataframe(counts, width="stretch", hide_index=True)


def render_review_pill(theorem_id: int) -> str:
    score = load_review_score(theorem_id)
    if score is None or score.get("overall") is None:
        return ""
    decision = f" · {h(score['decision'])}" if score.get("decision") else ""
    return f'<span class="review-pill">review {h(score["overall"])}/10{decision}</span>'


def render_proven_theorem(row: pd.Series) -> None:
    theorem_id = int(row["id"])
    review_pill = render_review_pill(theorem_id)
    st.markdown(
        f"""
<div class="proof-card">
  <div class="proof-title">{h(row["title"])}</div>
  <div class="proof-meta">{h(row["slug"])} · <span class="status-pill">PROVED</span> {review_pill}
  · {int(row["proved_attempts"])} proof attempts · {int(row["proved_claims"])} proved claims</div>
</div>
""",
        unsafe_allow_html=True,
    )
    with st.expander("Statement and proofs", expanded=False):
        st.markdown(str(row["statement_md"]))

        score = load_review_score(theorem_id)
        if score is not None:
            parts = []
            if score.get("overall") is not None:
                parts.append(f"Overall {h(score['overall'])}/10")
            if score.get("soundness") is not None:
                parts.append(f"Soundness {h(score['soundness'])}/4")
            if score.get("decision"):
                parts.append(h(score["decision"]))
            if parts:
                st.markdown(
                    f'<div class="small-note">Peer review ({h(score["reviewed_at"])}): '
                    + ", ".join(parts)
                    + "</div>",
                    unsafe_allow_html=True,
                )
            if score.get("summary"):
                st.caption(str(score["summary"]))

        paper = latest_artifact(theorem_id, "paper")
        if paper is not None:
            st.caption(f"Paper: {paper['path']}")

        proofs = proofs_for(theorem_id)
        claims = proved_claims_for(theorem_id)
        if proofs.empty and claims.empty:
            st.caption("No proof text recorded yet.")
        for _, proof in proofs.iterrows():
            strategy = val(proof["strategy"])
            model = val(proof["model"])
            st.markdown(f"**{h(val(proof['title']) or 'Proof')}**  \n"
                        f"<span class='small-note'>{h(proof['created_at'])}"
                        f"{' · ' + h(strategy) if strategy else ''}"
                        f"{' · ' + h(model) if model else ''}</span>",
                        unsafe_allow_html=True)
            st.markdown(str(proof["result_md"]))
        for _, claim in claims.iterrows():
            st.markdown(f"**Proved claim**  \n<span class='small-note'>{h(claim['created_at'])}</span>",
                        unsafe_allow_html=True)
            st.markdown(str(claim["claim_md"]))
            if val(claim["proof_sketch_md"]):
                st.markdown(str(claim["proof_sketch_md"]))


def render_dashboard() -> None:
    render_header()
    render_status_dashboard()

    search = st.text_input(
        "Search proofs",
        label_visibility="collapsed",
        placeholder="Search proven theorems and their proofs",
    )
    theorems = proven_theorems(search)
    if theorems.empty:
        if search:
            st.caption("No proven theorems match this search.")
        else:
            st.caption("No proven theorems yet. Proofs will appear here once recorded as PROVED.")
        return
    for _, row in theorems.iterrows():
        render_proven_theorem(row)

    if oidc_enabled() or auth_enabled():
        st.divider()
        if oidc_enabled():
            st.caption(f"Signed in as {current_user_email() or 'unknown user'}")
            st.button("Sign out", on_click=st.logout)
        elif st.button("Sign out"):
            st.session_state["authenticated"] = False
            st.rerun()


install_css()
require_login()
ensure_db()
render_dashboard()
