from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from thesius.app import app
from thesius.db import connect, rows, seed

runner = CliRunner()

SLUG = "exact-short-box-product-fiber-curve-intersection"

CANNED_LATEX = r"""\documentclass{article}
\begin{filecontents}{references.bib}
@article{lu2024aiscientist,
  title={The AI Scientist},
  author={Lu, Chris and others},
  journal={arXiv preprint arXiv:2408.06292},
  year={2024}
}
\end{filecontents}
\title{A Test Paper}
\begin{document}
\maketitle
\section{Introduction}
We study the theorem, following \citep{lu2024aiscientist}.
\paragraph{Disclosure.}
This manuscript was autonomously generated.
\bibliographystyle{iclr2024_conference}
\bibliography{references}
\end{document}"""

CANNED_REVIEW = {
    "Summary": "A test paper.",
    "Strengths": ["Honest reporting"],
    "Weaknesses": ["No new theorems"],
    "Originality": 2,
    "Quality": 2,
    "Clarity": 3,
    "Significance": 2,
    "Questions": ["What is next?"],
    "Limitations": ["Computational evidence only"],
    "Ethical Concerns": False,
    "Soundness": 2,
    "Presentation": 3,
    "Contribution": 2,
    "Overall": 4,
    "Confidence": 4,
    "Decision": "Reject",
}


def test_paper_write_no_compile(tmp_path: Path, monkeypatch):
    db = tmp_path / "codex.sqlite"
    seed(db)

    import thesius.paper.writeup as writeup

    monkeypatch.setattr(writeup, "create_client", lambda model: (object(), model))
    monkeypatch.setattr(writeup, "resolve_model", lambda model=None: "test-model")

    def fake_llm(msg, client, model, system_message, **kwargs):
        return f"```latex\n{CANNED_LATEX}\n```", []

    monkeypatch.setattr(writeup, "get_response_from_llm", fake_llm)
    monkeypatch.setattr(writeup, "run_chktex", lambda tex_path: "")

    out_dir = tmp_path / "papers"
    result = runner.invoke(app, [
        "paper", "write",
        "--theorem", SLUG,
        "--out-dir", str(out_dir),
        "--no-compile",
        "--db", str(db),
    ])
    assert result.exit_code == 0, result.output

    tex_path = out_dir / SLUG / "latex" / "template.tex"
    assert tex_path.exists()
    tex = tex_path.read_text()
    assert r"\end{document}" in tex
    assert "A Test Paper" in tex

    con = connect(db)
    try:
        artifacts = rows(con, "SELECT kind, path FROM artifact")
        assert any(a["kind"] == "paper_tex" for a in artifacts)
    finally:
        con.close()


def test_paper_review_text_file(tmp_path: Path, monkeypatch):
    db = tmp_path / "codex.sqlite"
    seed(db)

    import thesius.paper.llm as llm_mod
    import thesius.paper.review as review_mod

    monkeypatch.setattr(llm_mod, "create_client", lambda model: (object(), model))

    def fake_llm(msg, client, model, system_message, **kwargs):
        return (
            "THOUGHT:\nLooks like a test paper.\n\nREVIEW JSON:\n```json\n"
            + json.dumps(CANNED_REVIEW)
            + "\n```",
            [],
        )

    monkeypatch.setattr(review_mod, "get_response_from_llm", fake_llm)

    paper = tmp_path / "paper.txt"
    paper.write_text("A test paper about the exact short-box theorem. " * 20)

    result = runner.invoke(app, [
        "paper", "review", str(paper),
        "--theorem", SLUG,
        "--fewshot", "0",
        "--db", str(db),
    ])
    assert result.exit_code == 0, result.output
    assert "Reject" in result.output

    review_path = paper.with_suffix(".review.json")
    assert review_path.exists()
    saved = json.loads(review_path.read_text())
    assert saved["review"]["Overall"] == 4

    con = connect(db)
    try:
        artifacts = rows(con, "SELECT kind, theorem_id FROM artifact WHERE kind='paper_review'")
        assert len(artifacts) == 1
        assert artifacts[0]["theorem_id"] is not None
    finally:
        con.close()


def test_paper_feature_flag_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("THESIUS_FEATURE_PAPER", "0")
    db = tmp_path / "codex.sqlite"
    seed(db)
    result = runner.invoke(app, [
        "paper", "export",
        "--theorem", SLUG,
        "--out-dir", str(tmp_path / "papers"),
        "--db", str(db),
    ])
    assert result.exit_code == 1
    assert "features.paper" in result.output
    assert not (tmp_path / "papers").exists()


def test_paper_feature_flag_from_config(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("THESIUS_FEATURE_PAPER", raising=False)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["config", "set", "features.paper", "true"])
    assert result.exit_code == 0, result.output

    from thesius.settings import feature_enabled

    assert feature_enabled("paper") is True


def test_review_fewshot_examples_load():
    from thesius.paper.review import get_review_fewshot_examples

    prompt = get_review_fewshot_examples(1)
    assert "Paper:" in prompt and "Review:" in prompt
    assert len(prompt) > 1000
