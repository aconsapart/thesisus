from __future__ import annotations

from pathlib import Path

from thesius.settings import feature_enabled, get_database_path


def _write_config(tmp_path: Path, content: str) -> None:
    config = tmp_path / "config" / "local_cli_settings.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(content)


def test_legacy_database_key_matches_app_resolution(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("THESIUS_DB", raising=False)
    _write_config(tmp_path, '{"database": "legacy.sqlite"}')

    from thesius.app import _db_path

    assert get_database_path(None) == "legacy.sqlite"
    assert get_database_path(None) == _db_path(None)


def test_corrupt_config_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("THESIUS_DB", raising=False)
    monkeypatch.delenv("THESIUS_FEATURE_PAPER", raising=False)
    _write_config(tmp_path, "{not valid json")

    assert get_database_path(None) == "proof_codex.sqlite"
    assert feature_enabled("paper") is False
