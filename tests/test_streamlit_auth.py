from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "components" / "theorem_codex" / "apps" / "streamlit_app.py"


@pytest.fixture()
def app_test(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["streamlit_app.py", "--db", str(tmp_path / "codex.sqlite")])

    def make() -> AppTest:
        return AppTest.from_file(str(APP), default_timeout=30)

    return make


def has_password_field(at: AppTest) -> bool:
    return any(t.label == "Password" for t in at.text_input)


def main_ui_rendered(at: AppTest) -> bool:
    return any("Research projects" in str(m.value) for m in at.markdown)


def submit_login(at: AppTest, password: str) -> AppTest:
    next(t for t in at.text_input if t.label == "Password").set_value(password)
    next(b for b in at.button if b.label == "Sign in").set_value(True)
    return at.run()


def test_open_access_without_password(app_test, monkeypatch):
    monkeypatch.delenv("THESIUS_PASSWORD", raising=False)
    at = app_test().run()
    assert not at.exception
    assert main_ui_rendered(at)
    assert not has_password_field(at)


def test_gate_blocks_unauthenticated(app_test, monkeypatch):
    monkeypatch.setenv("THESIUS_PASSWORD", "s3cret")
    at = app_test().run()
    assert not at.exception
    assert has_password_field(at)
    assert not main_ui_rendered(at)


def test_wrong_password_rejected(app_test, monkeypatch):
    monkeypatch.setenv("THESIUS_PASSWORD", "s3cret")
    at = submit_login(app_test().run(), "wrong-password")
    assert any("Incorrect password" in str(e.value) for e in at.error)
    assert not main_ui_rendered(at)


def test_correct_password_signs_in(app_test, monkeypatch):
    monkeypatch.setenv("THESIUS_PASSWORD", "s3cret")
    at = submit_login(app_test().run(), "s3cret")
    assert not at.exception
    assert at.session_state["authenticated"] is True
    assert main_ui_rendered(at)
    assert not has_password_field(at)


def test_sign_out_returns_to_gate(app_test, monkeypatch):
    monkeypatch.setenv("THESIUS_PASSWORD", "s3cret")
    at = submit_login(app_test().run(), "s3cret")
    at.session_state["authenticated"] = False
    at.run()
    assert has_password_field(at)
    assert not main_ui_rendered(at)


def test_recovery_after_failed_attempt(app_test, monkeypatch):
    monkeypatch.setenv("THESIUS_PASSWORD", "s3cret")
    at = submit_login(app_test().run(), "nope")
    assert not main_ui_rendered(at)
    at = submit_login(at, "s3cret")
    assert main_ui_rendered(at)
    assert not has_password_field(at)


OIDC_SECRETS = {
    "client_id": "test-client",
    "client_secret": "test-secret",
    "redirect_uri": "http://localhost:8501/oauth2callback",
    "cookie_secret": "test-cookie-secret",
    "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
}


def test_oidc_gate_blocks_unauthenticated(app_test, monkeypatch):
    monkeypatch.delenv("THESIUS_PASSWORD", raising=False)
    at = app_test()
    at.secrets["auth"] = OIDC_SECRETS
    at.run()
    assert not at.exception
    assert any(b.label == "Sign in" for b in at.button)
    assert not main_ui_rendered(at)


def test_oidc_takes_precedence_over_password(app_test, monkeypatch):
    monkeypatch.setenv("THESIUS_PASSWORD", "s3cret")
    at = app_test()
    at.secrets["auth"] = OIDC_SECRETS
    at.run()
    assert not at.exception
    assert any(b.label == "Sign in" for b in at.button)
    assert not has_password_field(at)
    assert not main_ui_rendered(at)
