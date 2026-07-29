from __future__ import annotations

from dataclasses import dataclass, field, fields
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
class SearchSettings:
    """Machine-side limits for the counterexample search.

    The problem YAML says *what* to search; this says how much of the machine
    it may spend doing it. A problem's `refutation:` block overrides these.
    """

    max_evaluations: int = 5_000
    random_samples: int = 0
    seed: int = 20240729
    time_limit_s: float = 30.0
    max_witnesses: int = 3


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
    search: SearchSettings = field(default_factory=SearchSettings)
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
        search_data = data.get("search", {}) or {}
        cfg.llm = LLMSettings(**{**cfg.llm.__dict__, **llm_data})
        cfg.formalization = FormalizationSettings(**{**cfg.formalization.__dict__, **form_data})
        cfg.tools = ToolSettings(**{**cfg.tools.__dict__, **tool_data})
        cfg.search = SearchSettings(**{**cfg.search.__dict__, **search_data})
        return cfg

    def search_budget(self, overrides: dict[str, Any] | None = None) -> Any:
        """The effective search budget: machine defaults, then problem overrides."""
        from .tools.refutation import SearchBudget

        merged = {**self.search.__dict__, **(overrides or {})}
        return SearchBudget.from_dict(merged)

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
    """A problem to attack from both sides.

    `targets` are what we try to prove. `conjectures` are what we try to break:
    universally quantified claims with machine-checkable predicates, which the
    counterexample search can act on without an LLM in the loop. A problem may
    declare either or both; a problem with no conjectures still runs, but its
    refutation lane is limited to model-proposed witnesses.
    """

    slug: str
    title: str
    domain: str = "general"
    background: str = ""
    definitions: list[dict[str, Any]] = field(default_factory=list)
    targets: list[dict[str, Any]] = field(default_factory=list)
    conjectures: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    known_results: list[dict[str, Any]] = field(default_factory=list)
    current_frontier: str = ""
    falsification_tests: list[str] = field(default_factory=list)
    computation_tasks: list[str] = field(default_factory=list)
    formalization_targets: list[str] = field(default_factory=list)
    refutation: dict[str, Any] = field(default_factory=dict)
    prior_art: dict[str, Any] = field(default_factory=dict)
    source_path: str = ""

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ProblemSpec":
        p = Path(path)
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(
                f"{p}: unknown problem-spec key(s) {sorted(unknown)}; expected {sorted(known - {'source_path'})}"
            )
        return cls(source_path=str(p), **data)

    def build_conjectures(self) -> list[Any]:
        """Parse the declared conjectures into executable objects.

        Imported lazily so that loading a problem spec does not require SymPy
        in contexts that only read metadata (dashboards, seeding scripts).
        """
        from .conjecture import load_conjectures

        return load_conjectures(self.conjectures)

    def build_claims(self) -> list[Any]:
        """Parse the declared claims -- the contributions prior art can kill."""
        from .prior_art import load_claims

        return load_claims(self.claims)

    def prior_art_policy(self) -> Any:
        """How thorough a search has to be before its silence counts as evidence."""
        from .prior_art import PriorArtPolicy

        return PriorArtPolicy.from_dict(self.prior_art)


PROVE = "PROVE"
REFUTE = "REFUTE"
BOTH = "BOTH"
VALID_MODES = {PROVE, REFUTE, BOTH}


@dataclass
class StrategySpec:
    """A ranked lane.

    `mode` decides which side of the problem the lane works on. Before this
    field existed every lane was implicitly a proof lane that was merely *asked*
    to falsify first; a `REFUTE` lane is scheduled, prompted, and scored as a
    counterexample hunt in its own right.
    """

    id: str
    name: str
    rank: int
    description: str
    mode: str = PROVE
    allowed_tools: list[str] = field(default_factory=list)
    falsification_prompts: list[str] = field(default_factory=list)
    counterexample_prompts: list[str] = field(default_factory=list)
    proof_prompts: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    target_conjectures: list[str] = field(default_factory=list)
    status: str = "ACTIVE"
    score: float = 0.0

    def __post_init__(self) -> None:
        self.mode = str(self.mode).upper()
        if self.mode not in VALID_MODES:
            raise ValueError(
                f"strategy {self.id!r}: mode must be one of {sorted(VALID_MODES)}, got {self.mode!r}"
            )

    def refutes(self) -> bool:
        return self.mode in {REFUTE, BOTH}

    def proves(self) -> bool:
        return self.mode in {PROVE, BOTH}


@dataclass
class StrategyPortfolio:
    strategies: list[StrategySpec]

    @classmethod
    def from_yaml(cls, path: str | Path) -> "StrategyPortfolio":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        known = {f.name for f in fields(StrategySpec)}
        specs = []
        for raw in data.get("strategies", []):
            unknown = set(raw) - known
            if unknown:
                raise ValueError(
                    f"{path}: strategy {raw.get('id', '?')!r} has unknown key(s) {sorted(unknown)}"
                )
            specs.append(StrategySpec(**raw))
        return cls(strategies=specs)

    def active(self) -> list[StrategySpec]:
        return [s for s in self.strategies if s.status.upper() != "DEMOTED"]

    def top(self, n: int) -> list[StrategySpec]:
        return sorted(self.active(), key=lambda s: (s.rank, -s.score))[:n]

    def top_by_mode(self, n: int, *, refuting: bool) -> list[StrategySpec]:
        pool = [s for s in self.active() if (s.refutes() if refuting else s.proves())]
        return sorted(pool, key=lambda s: (s.rank, -s.score))[:n]
