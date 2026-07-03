from __future__ import annotations

import argparse
import hmac
import html
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from theorem_codex.db import (  # noqa: E402
    add_attempt,
    add_computation,
    connect,
    init_db,
    upsert_theorem,
)

STATUSES = ["FAILED/OPEN", "PROVED", "CONDITIONAL", "COMPUTATIONAL", "HEURISTIC", "FALSIFIED"]
PROJECT_KINDS = ["CONJECTURE", "THEOREM", "COMPUTATION_TARGET", "FRONTIER", "LEMMA"]
PANEL_HEIGHT = 900
STUDY_PROMPT_TEMPLATE = """You are a research-level analytic number theorist and finite-field combinatorics expert. Attack the following precise problem directly. Do not summarize previous work. Do not merely restate equivalences. Either prove the target, disprove it with an explicit infinite family, or reduce it to a strictly smaller named or newly isolated sublemma.

# Target problem: {{problem_title}}

{{problem_statement}}

{{proof_objective}}

# Required work

## 1. Expand the core counting or moment expression exactly

Write the central quantity as an exact count of tuples, incidences, fibers, or solutions. Derive the algebraic conditions without dropping exceptional cases. If the problem contains rational expressions, explicitly record denominator-zero cases.

## 2. Identify all degeneracies

List and handle every diagonal, symmetry, zero-denominator, tangent, vertical, horizontal, singular, or exceptional family. Prove that each degenerate family contributes within the target scale, or isolate a real obstruction.

## 3. Convert to a smaller algebraic equation

Derive the cleanest polynomial, rational, incidence, energy, or fiber equation equivalent to the main difficulty. Simplify it as much as possible and look for factorization, hidden symmetries, shifted-product structure, divisor structure, or point-plane incidence structure.

## 4. Try integer lifting or no-wrap ranges

Find any explicit range where the congruence or finite-field condition lifts to an integer equality. In that range, prove the strongest divisor, geometry-of-numbers, or elementary estimate available. Do not cite a divisor bound until the exact divisor expression has been derived.

## 5. Try incidence geometry

Look for point-line, point-plane, Cartesian-product, or image-set incidence formulations. If using Stevens-de Zeeuw, Rudnev, Murphy-Petridis-type identities, sum-product expansion, or related results, state the theorem exactly and verify all size and non-concentration hypotheses. Compute the exact loss if the theorem falls short.

## 6. Try a character-sum proof

Express the main count using additive or multiplicative characters. Identify the complete exponential sums that arise. Check irreducibility, non-degeneracy, diagonal components, additive-derivative obstructions, and interval-completion losses before invoking Weil, Deligne, or completion estimates.

## 7. Try a spectral, Fourier, or fiber-energy approach

Define the natural map or operator whose fiber energy is being estimated. Prove or disprove that its fibers over the structured input set have the desired second moment. Analyze hidden symmetries and exceptional high-multiplicity fibers.

## 8. Search for counterexamples

Try to construct explicit infinite counterexamples from degenerate parameters, symmetry, high-tangency configurations, large fibers, repeated points, critical ranges, or arithmetic concentration. A counterexample must exceed the claimed scale by a power of the main parameter, or show failure for every fixed polylogarithmic loss.

## 9. Split ranges

Give the strongest bound available in every natural parameter range. For each range, state the method, exact bound, whether it proves the target, and the bottleneck.

## 10. Desired final output

Return exactly one of the following:

### A. Complete proof

A full proof of the target estimate or statement.

### B. Counterexample

An explicit infinite family where the target fails.

### C. Strict reduction

A strictly smaller open lemma, stated cleanly, that is weaker and more focused than the original target. The reduction must be genuinely localized: algebraic, incidence-theoretic, divisor-theoretic, spectral, or exponential-sum based.
"""


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
  max-width: 100%;
}
div[data-testid="column"] {
  min-width: 0;
}
h1, h2, h3 {
  letter-spacing: 0;
}
.atlas-shell {
  border-bottom: 1px solid #ececec;
  padding: 0.1rem 0 0.55rem;
}
.atlas-title {
  font-size: 0.95rem;
  font-weight: 650;
}
.atlas-subtitle {
  color: #666;
  font-size: 0.78rem;
}
.panel {
  background: #fafafa;
  border: 1px solid #ececec;
  border-radius: 8px;
  padding: 0.85rem;
}
.left-panel {
  background: #f7f7f8;
  min-height: calc(100vh - 2.2rem);
}
.right-panel {
  background: #fbfbfb;
  min-height: calc(100vh - 2.2rem);
}
.section-label {
  color: #606060;
  font-size: 0.75rem;
  font-weight: 650;
  margin: 0.45rem 0 0.2rem;
  text-transform: uppercase;
}
.project-card {
  border: 1px solid #e9e9e9;
  border-radius: 8px;
  padding: 0.62rem 0.7rem;
  margin: 0.35rem 0;
  background: white;
}
.project-card.active {
  background: #eeeeef;
  border-color: #dedee0;
}
.project-title {
  font-size: 0.82rem;
  font-weight: 650;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
.project-meta {
  color: #777;
  font-size: 0.72rem;
  margin-top: 0.18rem;
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
.article {
  border-bottom: 1px solid #eeeeee;
  margin-bottom: 1rem;
  padding-bottom: 1rem;
}
.message-user {
  background: #080808;
  color: #fff;
  border-radius: 16px;
  margin: 0.35rem 0 0.35rem auto;
  max-width: 82%;
  padding: 0.78rem 0.9rem;
  white-space: pre-wrap;
}
.message-assistant {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  margin: 0.35rem 0 0.8rem;
  padding: 0.8rem 0.9rem;
  white-space: pre-wrap;
}
.activity-item {
  border-left: 2px solid #dedede;
  margin: 0.5rem 0;
  padding: 0.1rem 0 0.45rem 0.75rem;
}
.activity-title {
  font-size: 0.78rem;
  font-weight: 650;
}
.activity-meta {
  color: #777;
  font-size: 0.7rem;
}
.small-note {
  color: #777;
  font-size: 0.76rem;
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
.stButton > button {
  border-radius: 8px;
}
textarea {
  font-size: 0.87rem !important;
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
def q(sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    ensure_db()
    con = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()


def write(fn, *args, **kwargs):
    ensure_db()
    con = connect(DB_PATH)
    try:
        out = fn(con, *args, **kwargs)
        st.cache_data.clear()
        return out
    finally:
        con.close()


def h(text: Any) -> str:
    return html.escape("" if text is None else str(text))


def truncate(text: str | None, limit: int = 110) -> str:
    value = " ".join((text or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80].strip("-") or "problem"


def unique_theorem_slug(base: str) -> str:
    slug = slugify(base)
    existing = set(q("SELECT slug FROM theorem")["slug"].tolist())
    if slug not in existing:
        return slug
    for idx in range(2, 1000):
        candidate = f"{slug}-{idx}"
        if candidate not in existing:
            return candidate
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{slug}-{stamp}"


def render_study_prompt(template: str, *, title: str, slug: str, problem: str, objective: str) -> str:
    objective_text = f"# Proof objective / notes\n\n{objective}" if objective else ""
    return (
        template.replace("{{problem_title}}", title)
        .replace("{{problem_slug}}", slug)
        .replace("{{problem_statement}}", problem)
        .replace("{{proof_objective}}", objective_text)
    )


def theorem_projects(search: str = "") -> pd.DataFrame:
    like = f"%{search}%"
    if search:
        return q(
            """
            SELECT t.*,
                   (SELECT count(*) FROM computation c WHERE c.theorem_id=t.id) computations,
                   (SELECT count(*) FROM attempt a WHERE a.theorem_id=t.id) attempts
            FROM theorem t
            WHERE t.slug LIKE ? OR t.title LIKE ? OR t.statement_md LIKE ?
            ORDER BY t.is_frontier DESC, t.frontier_rank IS NULL, t.frontier_rank, t.updated_at DESC
            """,
            (like, like, like),
        )
    return q(
        """
        SELECT t.*,
               (SELECT count(*) FROM computation c WHERE c.theorem_id=t.id) computations,
               (SELECT count(*) FROM attempt a WHERE a.theorem_id=t.id) attempts
        FROM theorem t
        ORDER BY t.is_frontier DESC, t.frontier_rank IS NULL, t.frontier_rank, t.updated_at DESC
        """
    )


def current_project(slug: str | None) -> pd.Series | None:
    if not slug:
        return None
    df = q("SELECT * FROM theorem WHERE slug=?", (slug,))
    if df.empty:
        return None
    return df.iloc[0]


def project_attempts(theorem_id: int, limit: int = 8) -> pd.DataFrame:
    return q(
        """
        SELECT a.id, a.created_at, a.title, a.prompt_md, a.result_md, a.status, a.model, s.slug strategy
        FROM attempt a
        LEFT JOIN strategy s ON s.id=a.strategy_id
        WHERE a.theorem_id=?
        ORDER BY a.created_at DESC
        LIMIT ?
        """,
        (theorem_id, limit),
    )


def project_computations(theorem_id: int, limit: int = 10) -> pd.DataFrame:
    return q(
        """
        SELECT id, created_at, run_id, name, status, code_path, data_path, report_path, summary_json
        FROM computation
        WHERE theorem_id=?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (theorem_id, limit),
    )


def project_counts(theorem_id: int) -> dict[str, int]:
    values = {
        "attempts": q("SELECT count(*) count FROM attempt WHERE theorem_id=?", (theorem_id,)).iloc[0]["count"],
        "computations": q("SELECT count(*) count FROM computation WHERE theorem_id=?", (theorem_id,)).iloc[0]["count"],
        "claims": q("SELECT count(*) count FROM claim WHERE theorem_id=?", (theorem_id,)).iloc[0]["count"],
        "falsifications": q("SELECT count(*) count FROM falsification WHERE theorem_id=?", (theorem_id,)).iloc[0]["count"],
    }
    return {key: int(value) for key, value in values.items()}


def create_project(title: str, problem: str, objective: str, kind: str, status: str, importance: int, make_frontier: bool, prompt_template: str) -> str:
    slug = unique_theorem_slug(title)
    statement = problem if not objective else f"{problem}\n\n## Proof objective\n\n{objective}"
    frontier_count = int(q("SELECT count(*) count FROM theorem WHERE is_frontier=1").iloc[0]["count"])
    rank = frontier_count + 1 if make_frontier else None
    write(
        upsert_theorem,
        slug=slug,
        title=title,
        statement_md=statement,
        status=status,
        kind=kind,
        frontier_rank=rank,
        is_frontier=make_frontier,
        importance=importance,
    )
    run_id = "intake-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    rendered_prompt = render_study_prompt(prompt_template, title=title, slug=slug, problem=problem, objective=objective)
    write(
        add_computation,
        theorem_slug=slug,
        run_id=run_id,
        name=f"Proof task: {title}",
        status="FAILED/OPEN",
        summary={
            "source": "atlas_project_intake",
            "title": title,
            "slug": slug,
            "problem": problem,
            "objective": objective,
            "prompt_template": prompt_template,
            "rendered_prompt": rendered_prompt,
        },
    )
    write(
        add_attempt,
        theorem_slug=slug,
        strategy_slug=None,
        run_id=run_id,
        title=f"Study prompt: {title}",
        prompt_md=rendered_prompt,
        result_md="Created from the new-project prompt template. Awaiting proof, counterexample, or strict reduction.",
        status="FAILED/OPEN",
        model=None,
    )
    return slug


def queue_project_prompt(project: pd.Series, prompt: str, title: str, use_template: bool) -> None:
    run_id = "chat-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if use_template:
        rendered_prompt = render_study_prompt(
            STUDY_PROMPT_TEMPLATE,
            title=str(project["title"]),
            slug=str(project["slug"]),
            problem=f"{project['statement_md']}\n\n# Current task\n\n{prompt}",
            objective="",
        )
    else:
        rendered_prompt = prompt
    write(
        add_computation,
        theorem_slug=str(project["slug"]),
        run_id=run_id,
        name=title or f"Project prompt: {truncate(prompt, 56)}",
        status="FAILED/OPEN",
        summary={
            "source": "atlas_main_chat",
            "prompt": prompt,
            "rendered_prompt": rendered_prompt,
        },
    )
    write(
        add_attempt,
        theorem_slug=str(project["slug"]),
        strategy_slug=None,
        run_id=run_id,
        title=title or "Project prompt",
        prompt_md=rendered_prompt,
        result_md="Queued from the project chat. Awaiting proof, counterexample, or strict reduction.",
        status="FAILED/OPEN",
        model=None,
    )


def queue_side_question(project: pd.Series, question: str) -> None:
    run_id = "side-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    write(
        add_attempt,
        theorem_slug=str(project["slug"]),
        strategy_slug=None,
        run_id=run_id,
        title=f"Side question: {truncate(question, 72)}",
        prompt_md=question,
        result_md="Queued as a side question for this theorem project.",
        status="HEURISTIC",
        model=None,
    )


def render_metric_grid(counts: dict[str, int]) -> None:
    st.markdown(
        f"""
<div class="metric-grid">
  <span><strong>{counts["computations"]}</strong>runs</span>
  <span><strong>{counts["attempts"]}</strong>attempts</span>
  <span><strong>{counts["claims"]}</strong>claims</span>
  <span><strong>{counts["falsifications"]}</strong>blocks</span>
</div>
""",
        unsafe_allow_html=True,
    )


def render_left_panel() -> None:
    with st.container(border=True, height=PANEL_HEIGHT):
        st.markdown('<div class="atlas-title">Theorem Codex</div><div class="atlas-subtitle">Research projects</div>', unsafe_allow_html=True)
        if st.button("New project", width="stretch"):
            st.session_state["new_project_mode"] = True
            st.rerun()
        search = st.text_input("Search projects", label_visibility="collapsed", placeholder="Search projects")
        projects = theorem_projects(search)
        st.markdown('<div class="section-label">Projects</div>', unsafe_allow_html=True)
        if projects.empty:
            st.caption("No theorem projects yet.")
        else:
            slugs = projects["slug"].tolist()
            title_by_slug = dict(zip(projects["slug"], projects["title"]))
            current_slug = st.session_state.get("selected_slug")
            index = slugs.index(current_slug) if current_slug in slugs else 0
            chosen = st.selectbox(
                "Project",
                slugs,
                index=index,
                format_func=lambda slug: truncate(str(title_by_slug.get(slug, slug)), 44),
                label_visibility="collapsed",
            )
            if chosen != current_slug or st.session_state.get("new_project_mode"):
                st.session_state["selected_slug"] = chosen
                st.session_state["new_project_mode"] = False
                st.rerun()
            row = projects[projects["slug"].eq(chosen)].iloc[0]
            st.markdown(
                f"""
<div class="project-card active">
  <div class="project-title">{h(truncate(row["title"], 70))}</div>
  <div class="project-meta">{h(row["status"])} · {int(row["computations"])} runs · {int(row["attempts"])} attempts</div>
</div>
""",
                unsafe_allow_html=True,
            )
        st.divider()
        st.markdown('<div class="section-label">Database</div>', unsafe_allow_html=True)
        st.code(str(DB_PATH), language=None)


def render_new_project() -> None:
    st.markdown('<div class="atlas-shell"><div class="atlas-title">New theorem project</div><div class="atlas-subtitle">Paste a conjecture or problem and create a proof workspace.</div></div>', unsafe_allow_html=True)
    with st.form("new_project_form"):
        title = st.text_input("Project title")
        problem = st.text_area("Conjecture or problem to prove", height=240)
        objective = st.text_area("Proof objective / notes", height=100)
        c1, c2, c3 = st.columns(3)
        with c1:
            kind = st.selectbox("Kind", PROJECT_KINDS)
        with c2:
            status = st.selectbox("Initial status", ["FAILED/OPEN", "HEURISTIC", "COMPUTATIONAL"])
        with c3:
            importance = st.slider("Importance", 1, 5, 3)
        make_frontier = st.checkbox("Add to current frontier", value=True)
        prompt_template = st.text_area("Study prompt template", value=STUDY_PROMPT_TEMPLATE, height=260)
        submitted = st.form_submit_button("Create project and computation")
    if submitted:
        if not title or not problem:
            st.error("Project title and problem text are required.")
            return
        slug = create_project(title, problem, objective, kind, status, importance, make_frontier, prompt_template)
        st.session_state["selected_slug"] = slug
        st.session_state["new_project_mode"] = False
        st.success(f"Created project `{slug}`.")
        st.rerun()


def render_chat(project: pd.Series) -> None:
    st.markdown(
        f"""
<div class="atlas-shell">
  <div class="atlas-title">{h(project["title"])}</div>
  <div class="atlas-subtitle">{h(project["slug"])} · <span class="status-pill">{h(project["status"])}</span></div>
</div>
""",
        unsafe_allow_html=True,
    )
    with st.expander("Project statement", expanded=True):
        st.markdown(str(project["statement_md"]))

    attempts = project_attempts(int(project["id"]), 8)
    st.markdown("### Main chat")
    if attempts.empty:
        st.caption("No prompts have been queued for this project yet.")
    else:
        for _, row in attempts.iloc[::-1].iterrows():
            prompt = row["prompt_md"] or row["title"] or "Prompt"
            result = row["result_md"] or ""
            st.markdown(f'<div class="message-user">{h(truncate(prompt, 1400))}</div>', unsafe_allow_html=True)
            st.markdown(
                f"""
<div class="message-assistant">
  <strong>{h(row["title"] or "Research result")}</strong><br>
  <span class="small-note">{h(row["status"])} · {h(row["created_at"])}</span><br><br>
  {h(truncate(result, 1400))}
</div>
""",
                unsafe_allow_html=True,
            )

    with st.form("project_chat_form"):
        prompt = st.text_area("Ask anything", placeholder="Ask this theorem project anything, paste a proof task, or request a reduction.", height=95)
        with st.expander("Options", expanded=False):
            title = st.text_input("Optional run title")
            use_template = st.checkbox("Use study template", value=True)
        submitted = st.form_submit_button("Queue computation")
    if submitted:
        if not prompt:
            st.error("Enter a prompt first.")
        else:
            queue_project_prompt(project, prompt, title, use_template)
            st.success("Queued computation and linked attempt.")
            st.rerun()


def render_activity_item(title: str, meta: str) -> None:
    st.markdown(
        f"""
<div class="activity-item">
  <div class="activity-title">{h(title)}</div>
  <div class="activity-meta">{h(meta)}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_right_panel(project: pd.Series | None) -> None:
    with st.container(border=True, height=PANEL_HEIGHT):
        st.markdown('<div class="atlas-title">Activity</div>', unsafe_allow_html=True)
        if project is None:
            st.caption("Create or open a theorem project to see progress.")
            return

        counts = project_counts(int(project["id"]))
        render_metric_grid(counts)

        with st.expander("Ask side question", expanded=False):
            with st.form("side_question_form"):
                question = st.text_area("Question", label_visibility="collapsed", placeholder="Ask a narrower side question about this theorem.", height=95)
                submitted = st.form_submit_button("Queue")
            if submitted:
                if not question:
                    st.error("Enter a side question first.")
                else:
                    queue_side_question(project, question)
                    st.success("Side question queued.")
                    st.rerun()

        with st.expander("Recent activity", expanded=True):
            st.markdown('<div class="section-label">Computations</div>', unsafe_allow_html=True)
            computations = project_computations(int(project["id"]), 4)
            if computations.empty:
                st.caption("No computations yet.")
            else:
                for _, row in computations.iterrows():
                    render_activity_item(row["name"], f"{row['status']} · {row['created_at']}")

            st.markdown('<div class="section-label">Proof work</div>', unsafe_allow_html=True)
            attempts = project_attempts(int(project["id"]), 4)
            if attempts.empty:
                st.caption("No attempts yet.")
            else:
                for _, row in attempts.iterrows():
                    render_activity_item(row["title"] or "Untitled attempt", f"{row['status']} · {row['created_at']}")

        with st.expander("Project data"):
            st.dataframe(project_computations(int(project["id"]), 25), width="stretch", hide_index=True)
            st.dataframe(project_attempts(int(project["id"]), 25), width="stretch", hide_index=True)

        with st.expander("Settings"):
            st.code(str(DB_PATH), language=None)
            if oidc_enabled():
                st.caption(f"Signed in as {current_user_email() or 'unknown user'}")
                st.button("Sign out", on_click=st.logout)
            elif auth_enabled() and st.button("Sign out"):
                st.session_state["authenticated"] = False
                st.rerun()
            if st.button("Initialize schema"):
                init_db(DB_PATH)
                st.cache_data.clear()
                st.success("Initialized schema.")
            sql = st.text_area("SQL", "SELECT * FROM v_current_frontier;", height=100)
            if st.button("Run SQL"):
                try:
                    st.dataframe(q(sql), width="stretch")
                except Exception as exc:
                    st.error(str(exc))


def default_selected_project() -> str | None:
    projects = theorem_projects()
    if projects.empty:
        return None
    return str(projects.iloc[0]["slug"])


install_css()
require_login()
ensure_db()

if "new_project_mode" not in st.session_state:
    st.session_state["new_project_mode"] = False
if "selected_slug" not in st.session_state:
    st.session_state["selected_slug"] = default_selected_project()

selected = current_project(st.session_state.get("selected_slug"))
if selected is None and not st.session_state["new_project_mode"]:
    st.session_state["new_project_mode"] = True

left, center, right = st.columns([0.24, 0.52, 0.24], gap="small")

with left:
    render_left_panel()

with center:
    with st.container(border=True, height=PANEL_HEIGHT):
        if st.session_state.get("new_project_mode"):
            render_new_project()
        elif selected is not None:
            render_chat(selected)
        else:
            st.info("Create a theorem project to begin.")

with right:
    render_right_panel(None if st.session_state.get("new_project_mode") else selected)
