from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from thesius.app import app
from thesius.db import add_artifact, add_attempt, add_falsification, connect, seed
from thesius.paper.export import codex_to_notes

runner = CliRunner()

SLUG = "exact-short-box-product-fiber-curve-intersection"

# A 1x1 transparent PNG.
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffffff7f000905fe02fea8d4bd0000000049454e44ae426082"
)


def _seeded_db(tmp_path: Path) -> Path:
    db = tmp_path / "codex.sqlite"
    seed(db)
    return db


def test_codex_to_notes_exports_everything(tmp_path: Path):
    db = _seeded_db(tmp_path)
    report = tmp_path / "cas_degeneracy_report.md"
    report.write_text("# CAS report\nAll pairwise degeneracies checked.\n")
    figure = tmp_path / "degeneracy_plot.png"
    figure.write_bytes(PNG_BYTES)

    con = connect(db)
    try:
        add_attempt(
            con,
            theorem_slug=SLUG,
            strategy_slug="hybrid-combined-attack",
            run_id="run-1",
            title="First hybrid attack",
            prompt_md="Attack the fiber curve intersection.",
            result_md="Reduced to a shifted-product character sum.",
            status="HEURISTIC",
        )
        add_falsification(
            con,
            theorem_slug=SLUG,
            strategy_slug="near-injectivity",
            obstruction_md="Collision energy blows up in the very-short range.",
            counterexample_md="p=q=3 family",
            severity="HIGH",
        )
        con.execute(
            "INSERT INTO computation(theorem_id, run_id, name, status, report_path, summary_json) "
            "SELECT id, 'run-1', 'pairwise-degeneracy', 'COMPUTATIONAL', ?, ? FROM theorem WHERE slug=?",
            (str(report), json.dumps({"checked": 128, "degenerate": 0}), SLUG),
        )
        con.commit()
        add_artifact(con, path=str(figure), kind="figure", theorem_slug=SLUG)
        # A previously generated paper must NOT be re-exported as a figure.
        old_paper = tmp_path / "old-paper.pdf"
        old_paper.write_bytes(b"%PDF-1.4 fake")
        add_artifact(con, path=str(old_paper), kind="paper", theorem_slug=SLUG)

        export = codex_to_notes(con, SLUG, tmp_path / "out")
    finally:
        con.close()

    notes = export["notes_path"].read_text()
    assert "Exact Short-Box Product-Fiber Curve-Intersection Theorem" in notes
    assert "First hybrid attack" in notes
    assert "Collision energy blows up" in notes
    assert "pairwise-degeneracy" in notes
    assert "All pairwise degeneracies checked." in notes
    assert "degeneracy_plot.png" in notes

    results = json.loads(export["results_path"].read_text())
    assert results["counts"] == {
        "claims": 0,
        "attempts": 1,
        "falsifications": 1,
        "computations": 1,
    }
    assert results["figures"] == ["degeneracy_plot.png"]
    assert (tmp_path / "out" / "degeneracy_plot.png").exists()
    assert not (tmp_path / "out" / "old-paper.pdf").exists()


def test_codex_to_notes_unknown_slug(tmp_path: Path):
    db = _seeded_db(tmp_path)
    con = connect(db)
    try:
        try:
            codex_to_notes(con, "no-such-theorem", tmp_path / "out")
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "no-such-theorem" in str(exc)
    finally:
        con.close()


def test_paper_export_cli(tmp_path: Path):
    db = _seeded_db(tmp_path)
    out_dir = tmp_path / "papers"
    result = runner.invoke(app, [
        "paper", "export",
        "--theorem", SLUG,
        "--out-dir", str(out_dir),
        "--db", str(db),
    ])
    assert result.exit_code == 0, result.output
    assert (out_dir / SLUG / "notes.txt").exists()
    assert (out_dir / SLUG / "results.json").exists()
