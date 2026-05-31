from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from thesius.app import app
from thesius.db import connect, table_count

runner = CliRunner()


def test_init_and_status(tmp_path: Path):
    db = tmp_path / "codex.sqlite"
    result = runner.invoke(app, ["init", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert db.exists()
    con = connect(db)
    try:
        assert table_count(con, "theorem") >= 3
        assert table_count(con, "strategy") >= 3
    finally:
        con.close()

    result = runner.invoke(app, ["status", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "Codex status" in result.output
    assert "theorem" in result.output


def test_frontier_and_strategy_commands(tmp_path: Path):
    db = tmp_path / "codex.sqlite"
    runner.invoke(app, ["init", "--db", str(db)])

    result = runner.invoke(app, ["frontier", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "exact-short-box-product-fiber-curve-intersection" in result.output

    result = runner.invoke(app, ["strategies", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "hybrid-combined-attack" in result.output


def test_add_theorem_and_show(tmp_path: Path):
    db = tmp_path / "codex.sqlite"
    runner.invoke(app, ["init", "--db", str(db), "--no-seed"])

    result = runner.invoke(app, [
        "add", "theorem",
        "--slug", "test-theorem",
        "--title", "Test Theorem",
        "--statement", "A test statement.",
        "--status", "FAILED/OPEN",
        "--frontier",
        "--frontier-rank", "1",
        "--db", str(db),
    ])
    assert result.exit_code == 0, result.output
    assert "Saved theorem" in result.output

    result = runner.invoke(app, ["theorem", "test-theorem", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "A test statement" in result.output


def test_add_attempt(tmp_path: Path):
    db = tmp_path / "codex.sqlite"
    runner.invoke(app, ["init", "--db", str(db)])

    result = runner.invoke(app, [
        "add", "attempt",
        "--theorem", "exact-short-box-product-fiber-curve-intersection",
        "--strategy", "hybrid-combined-attack",
        "--status", "HEURISTIC",
        "--result", "This is a test attempt.",
        "--db", str(db),
    ])
    assert result.exit_code == 0, result.output
    assert "Added attempt" in result.output
    con = connect(db)
    try:
        assert table_count(con, "attempt") == 1
    finally:
        con.close()


def test_scripted_tui(tmp_path: Path):
    db = tmp_path / "codex.sqlite"
    result = runner.invoke(app, ["tui", "--db", str(db), "--commands", "status;frontier;strategies;quit"])
    assert result.exit_code == 0, result.output
    assert "Thesius TUI" in result.output
    assert "Current Frontier" in result.output
    assert "hybrid-combined-attack" in result.output


def test_config_set_show(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["config", "set", "model", "gpt-4.1"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0, result.output
    assert "gpt-4.1" in result.output


def test_database_path_from_config(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    configured_db = tmp_path / "configured.sqlite"

    result = runner.invoke(app, ["config", "set-db", str(configured_db)])
    assert result.exit_code == 0, result.output
    assert "Set default database" in result.output

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert configured_db.exists()
    assert str(configured_db) in result.output

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert str(configured_db) in result.output
    assert "theorem" in result.output


def test_db_argument_overrides_config(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    configured_db = tmp_path / "configured.sqlite"
    explicit_db = tmp_path / "explicit.sqlite"

    runner.invoke(app, ["config", "set-db", str(configured_db)])
    result = runner.invoke(app, ["init", "--db", str(explicit_db)])

    assert result.exit_code == 0, result.output
    assert explicit_db.exists()
    assert not configured_db.exists()
    assert str(explicit_db) in result.output


def test_configured_db_path_is_used(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    configured = tmp_path / "configured.sqlite"

    result = runner.invoke(app, ["config", "set-db", str(configured)])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["config", "get-db"])
    assert result.exit_code == 0, result.output
    assert str(configured) in result.output

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert configured.exists()

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert str(configured) in result.output


def test_init_save_db_option(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "saved_by_init.sqlite"

    result = runner.invoke(app, ["init", "--db", str(db), "--save-db"])
    assert result.exit_code == 0, result.output
    assert db.exists()

    result = runner.invoke(app, ["config", "get-db"])
    assert result.exit_code == 0, result.output
    assert str(db) in result.output


def test_configured_database_path_is_used(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    configured_db = tmp_path / "configured" / "codex.sqlite"

    result = runner.invoke(app, ["config", "set-db", str(configured_db)])
    assert result.exit_code == 0, result.output
    assert "Default database set" in result.output

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert configured_db.exists()

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert str(configured_db) in result.output


def test_configured_database_path_can_be_overridden_by_db_option(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    configured_db = tmp_path / "configured.sqlite"
    override_db = tmp_path / "override.sqlite"

    result = runner.invoke(app, ["config", "set-db", str(configured_db)])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["init", "--db", str(override_db)])
    assert result.exit_code == 0, result.output
    assert override_db.exists()
    assert not configured_db.exists()
