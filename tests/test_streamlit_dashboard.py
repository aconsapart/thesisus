from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from thesius.db import add_artifact, add_attempt, connect, init_db, upsert_theorem

APP = Path(__file__).resolve().parents[1] / "components" / "theorem_codex" / "apps" / "streamlit_app.py"


def _seed(tmp_path: Path) -> Path:
    db = tmp_path / "codex.sqlite"
    init_db(db)
    con = connect(db)
    try:
        upsert_theorem(
            con,
            slug="proved-thm",
            title="A Proven Theorem",
            statement_md="Statement about widgets.",
            status="PROVED",
        )
        upsert_theorem(
            con,
            slug="open-thm",
            title="An Open Problem",
            statement_md="Still open.",
            status="FAILED/OPEN",
        )
        add_attempt(
            con,
            theorem_slug="proved-thm",
            strategy_slug=None,
            run_id="run-1",
            title="Main proof",
            prompt_md="",
            result_md="By induction on widgets.",
            status="PROVED",
        )
        # Hostile title: must be escaped, never rendered as live HTML.
        add_attempt(
            con,
            theorem_slug="proved-thm",
            strategy_slug=None,
            run_id="run-2",
            title='<img src=x onerror=alert(1)>evil',
            prompt_md="",
            result_md="Second proof.",
            status="PROVED",
        )
        # A PROVED attempt on a NON-proven theorem: must not surface anywhere,
        # including the headline metrics.
        add_attempt(
            con,
            theorem_slug="open-thm",
            strategy_slug=None,
            run_id="run-3",
            title="Stray proved attempt",
            prompt_md="",
            result_md="Should not surface.",
            status="PROVED",
        )
        review = tmp_path / "proved-thm.review.json"
        review.write_text(json.dumps({"review": {
            "Overall": 8, "Decision": "Accept", "Soundness": 3, "Summary": "Solid.",
        }}))
        add_artifact(con, path=str(review), kind="paper_review", theorem_slug="proved-thm")
    finally:
        con.close()
    return db


@pytest.fixture()
def dashboard(tmp_path: Path, monkeypatch):
    db = _seed(tmp_path)
    monkeypatch.delenv("THESIUS_PASSWORD", raising=False)
    monkeypatch.setattr(sys, "argv", ["streamlit_app.py", "--db", str(db)])

    def make() -> AppTest:
        at = AppTest.from_file(str(APP), default_timeout=30)
        # Mask any real .streamlit/secrets.toml so tests run without auth.
        at.secrets["thesius_password"] = ""
        return at

    return make


def _markdown_text(at: AppTest) -> str:
    return "\n".join(str(m.value) for m in at.markdown)


def test_shows_only_proven_theorems(dashboard):
    at = dashboard().run()
    assert not at.exception
    text = _markdown_text(at)
    assert "A Proven Theorem" in text
    assert "An Open Problem" not in text
    assert "Should not surface." not in text
    assert "By induction on widgets." in text
    # SQL NULLs (model/strategy) must never render as "nan".
    assert "nan" not in text


def test_hostile_titles_are_escaped(dashboard):
    at = dashboard().run()
    text = _markdown_text(at)
    assert "<img src=x" not in text
    assert "&lt;img src=x" in text


def test_metrics_scoped_to_proven_theorems(dashboard):
    at = dashboard().run()
    text = _markdown_text(at)
    # 1 proven theorem; 2 proofs (both on the proven theorem — the stray
    # PROVED attempt on the open theorem must not count).
    assert "<strong>1</strong>proven theorems" in text
    assert "<strong>2</strong>proofs on record" in text


def test_shows_review_score(dashboard):
    at = dashboard().run()
    assert "review 8/10" in _markdown_text(at)
    assert "Accept" in _markdown_text(at)


def test_search_filters_proofs(dashboard):
    at = dashboard().run()
    search = next(t for t in at.text_input if t.label == "Search proofs")
    search.set_value("induction").run()
    assert "A Proven Theorem" in _markdown_text(at)

    at = dashboard().run()
    search = next(t for t in at.text_input if t.label == "Search proofs")
    search.set_value("no-such-proof-text").run()
    assert "A Proven Theorem" not in _markdown_text(at)


def test_search_never_surfaces_non_proven(dashboard):
    at = dashboard().run()
    search = next(t for t in at.text_input if t.label == "Search proofs")
    # Matches only the open theorem's text and its stray PROVED attempt.
    search.set_value("Still open").run()
    text = _markdown_text(at)
    assert "An Open Problem" not in text
    assert "A Proven Theorem" not in text


def test_search_treats_underscores_literally(dashboard):
    at = dashboard().run()
    search = next(t for t in at.text_input if t.label == "Search proofs")
    # With unescaped LIKE, "w_d" would wildcard-match "wid(gets)".
    search.set_value("w_d").run()
    assert "A Proven Theorem" not in _markdown_text(at)


def test_no_prompting_or_mutating_ui(dashboard):
    at = dashboard().run()
    # The dashboard is read-only: no forms, no text areas (SQL console,
    # prompt boxes), no buttons (open access → not even sign-out), and the
    # single text input is the proof search.
    assert list(at.text_area) == []
    assert list(at.button) == []
    labels = [t.label for t in at.text_input]
    assert labels == ["Search proofs"]
