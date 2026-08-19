from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def enable_paper_feature(monkeypatch):
    """Enable the paper feature flag for tests; individual tests may override."""
    monkeypatch.setenv("THESIUS_FEATURE_PAPER", "1")
