"""Make `math_workbench` importable without installing the package.

These tests deliberately avoid importing `math_workbench.agent`, so the whole
refutation track can be tested with only sympy and pyyaml present -- no
langchain, no langgraph, no API key.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

COMPONENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(COMPONENT_ROOT / "src"))


@pytest.fixture
def examples_dir() -> Path:
    return COMPONENT_ROOT / "examples"


@pytest.fixture
def demo_problem(examples_dir: Path) -> Path:
    return examples_dir / "counterexample_demo_problem.yaml"
