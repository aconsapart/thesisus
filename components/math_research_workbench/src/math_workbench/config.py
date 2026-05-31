from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml


@dataclass
class LLMSettings:
    provider: str = "openai"
    model: str = "gpt-4.1"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.2


@dataclass
class FormalizationSettings:
    lean_cmd: str = ""
    aristotle_cli: str = "aristotle"
    aristotle_api_key: str = ""


@dataclass
class ToolSettings:
    sage_cmd: str = "sage"
    magma_cmd: str = "magma"


@dataclass
class AppConfig:
    """Local runtime settings.

    Configuration precedence is:
      1. YAML config file (default config/local_settings.yaml or MATH_WORKBENCH_CONFIG)
      2. environment variable fallback for compatibility
      3. built-in defaults

    The YAML file is intended for local-only development and should not be committed.
    """

    llm: LLMSettings = field(default_factory=LLMSettings)
    formalization: FormalizationSettings = field(default_factory=FormalizationSettings)
    tools: ToolSettings = field(default_factory=ToolSettings)
    source_path: str = ""

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> "AppConfig":
        import os

        if path is None:
            path = os.environ.get("MATH_WORKBENCH_CONFIG", "config/local_settings.yaml")
        p = Path(path)
        cfg = cls(source_path=str(p))
        if not p.exists():
            return cfg
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        llm_data = data.get("llm", {}) or {}
        form_data = data.get("formalization", {}) or {}
        tool_data = data.get("tools", {}) or {}
        cfg.llm = LLMSettings(**{**cfg.llm.__dict__, **llm_data})
        cfg.formalization = FormalizationSettings(**{**cfg.formalization.__dict__, **form_data})
        cfg.tools = ToolSettings(**{**cfg.tools.__dict__, **tool_data})
        return cfg

    def openai_api_key(self) -> str:
        import os
        return self.llm.api_key or os.environ.get("OPENAI_API_KEY", "")

    def model_name(self) -> str:
        import os
        return self.llm.model or os.environ.get("MODEL_NAME", "gpt-4.1")

    def lean_cmd(self) -> str:
        import os
        return self.formalization.lean_cmd or os.environ.get("LEAN_CMD", "")

    def aristotle_cli(self) -> str:
        import os
        return self.formalization.aristotle_cli or os.environ.get("ARISTOTLE_CLI", "") or "aristotle"

    def aristotle_api_key(self) -> str:
        import os
        return self.formalization.aristotle_api_key or os.environ.get("ARISTOTLE_API_KEY", "")


def load_app_config(path: str | Path | None = None) -> AppConfig:
    return AppConfig.from_yaml(path)


@dataclass
class ProblemSpec:
    slug: str
    title: str
    domain: str = "general"
    background: str = ""
    definitions: list[dict[str, Any]] = field(default_factory=list)
    targets: list[dict[str, Any]] = field(default_factory=list)
    known_results: list[dict[str, Any]] = field(default_factory=list)
    current_frontier: str = ""
    falsification_tests: list[str] = field(default_factory=list)
    computation_tasks: list[str] = field(default_factory=list)
    formalization_targets: list[str] = field(default_factory=list)
    source_path: str = ""

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ProblemSpec":
        p = Path(path)
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return cls(source_path=str(p), **data)


@dataclass
class StrategySpec:
    id: str
    name: str
    rank: int
    description: str
    allowed_tools: list[str] = field(default_factory=list)
    falsification_prompts: list[str] = field(default_factory=list)
    proof_prompts: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    status: str = "ACTIVE"
    score: float = 0.0


@dataclass
class StrategyPortfolio:
    strategies: list[StrategySpec]

    @classmethod
    def from_yaml(cls, path: str | Path) -> "StrategyPortfolio":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(strategies=[StrategySpec(**s) for s in data.get("strategies", [])])

    def top(self, n: int) -> list[StrategySpec]:
        active = [s for s in self.strategies if s.status.upper() != "DEMOTED"]
        return sorted(active, key=lambda s: (s.rank, -s.score))[:n]
