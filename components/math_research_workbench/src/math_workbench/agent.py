from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .config import ProblemSpec, StrategyPortfolio, load_app_config
from .prompts import SYSTEM_PROMPT, SELECT_STRATEGIES_TEMPLATE, STRATEGY_LANE_TEMPLATE, SYNTHESIS_TEMPLATE, DISCOVERY_TEMPLATE, FORMAL_TASK_TEMPLATE
from .state import WorkbenchState
from .tools.cas import symbolic_core_checks, cas_pairwise_degeneracy
from .tools.codex import connect, init_db, upsert_problem, upsert_strategy, insert_attempt, insert_computation, insert_theorem
from .tools.formalization import run_local_lean, run_aristotle_cli


def llm_call(prompt: str) -> str:
    """Call the configured chat model.

    Reads config/local_settings.yaml by default, or the path in MATH_WORKBENCH_CONFIG.
    The local config values are used first; environment variables remain a fallback.
    """
    cfg = load_app_config()
    kwargs: dict[str, Any] = {
        "model": cfg.model_name(),
        "temperature": cfg.llm.temperature,
    }
    api_key = cfg.openai_api_key()
    if api_key:
        kwargs["api_key"] = api_key
    if cfg.llm.base_url:
        kwargs["base_url"] = cfg.llm.base_url
    llm = ChatOpenAI(**kwargs)
    resp = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])
    return str(resp.content)


def problem_summary(problem: dict[str, Any]) -> str:
    defs = "\n".join([f"- {d.get('name')}: {d.get('statement')}" for d in problem.get("definitions", [])])
    targets = "\n".join([f"- {t.get('id','target')}: {t.get('statement')}" for t in problem.get("targets", [])])
    return f"""
Title: {problem.get('title')}
Domain: {problem.get('domain')}

Background:
{problem.get('background','')}

Definitions:
{defs}

Targets:
{targets}

Known results:
{json.dumps(problem.get('known_results', []), indent=2)}
"""


def write_iter_file(state: WorkbenchState, name: str, text: str) -> str:
    d = Path(state["out_dir"]) / f"iteration_{state['iteration']:02d}"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def node_select_strategies(state: WorkbenchState) -> dict[str, Any]:
    strategies = sorted(state["strategies"], key=lambda s: (s.get("rank", 100), -s.get("score", 0)))
    active = strategies[: state["parallel_strategies"]]
    prompt = SELECT_STRATEGIES_TEMPLATE.format(
        problem_summary=problem_summary(state["problem"]),
        frontier=state["current_frontier"],
        strategies=json.dumps(strategies, indent=2),
        k=state["parallel_strategies"],
    )
    result = llm_call(prompt)
    write_iter_file(state, "selected_strategies.md", result)
    return {"active_strategies": active, "selected_report": result}


def node_run_strategies(state: WorkbenchState) -> dict[str, Any]:
    reports = []
    con = connect(state["db_path"])
    problem_id = upsert_problem(con, state["problem"])
    strategy_id_map = {s["id"]: upsert_strategy(con, s) for s in state["strategies"]}

    for strategy in state["active_strategies"]:
        prompt = STRATEGY_LANE_TEMPLATE.format(
            problem_summary=problem_summary(state["problem"]),
            frontier=state["current_frontier"],
            id=strategy["id"],
            name=strategy.get("name", strategy["id"]),
            description=strategy.get("description", ""),
            tools=", ".join(strategy.get("allowed_tools", [])),
            falsification_prompts="\n".join([f"- {x}" for x in strategy.get("falsification_prompts", [])]),
            proof_prompts="\n".join([f"- {x}" for x in strategy.get("proof_prompts", [])]),
            success_criteria="\n".join([f"- {x}" for x in strategy.get("success_criteria", [])]),
            failure_modes="\n".join([f"- {x}" for x in strategy.get("failure_modes", [])]),
        )
        result = llm_call(prompt)
        filename = f"strategy_{strategy['id']}.md"
        path = write_iter_file(state, filename, result)
        insert_attempt(con, problem_id, state["run_id"], state["iteration"], strategy_id_map.get(strategy["id"]), prompt, result, status="HEURISTIC")
        reports.append({"strategy": strategy["id"], "path": path, "report": result})

    con.close()
    batch = "\n\n".join([f"# {r['strategy']}\n\n{r['report']}" for r in reports])
    write_iter_file(state, "strategy_batch_report.md", batch)
    return {"strategy_reports": reports}


def node_symbolic_checks(state: WorkbenchState) -> dict[str, Any]:
    result = symbolic_core_checks()
    path = write_iter_file(state, "symbolic_checks.md", result)
    con = connect(state["db_path"])
    pid = upsert_problem(con, state["problem"])
    insert_computation(con, pid, state["run_id"], state["iteration"], "symbolic_core_checks", result, code_path="src/math_workbench/tools/cas.py", report_path=path)
    con.close()
    return {"symbolic_report": result}


def node_cas_degeneracy(state: WorkbenchState) -> dict[str, Any]:
    out = Path(state["out_dir"]) / "cas" / f"it{state['iteration']:02d}_pairwise"
    report = cas_pairwise_degeneracy(str(out))
    md = (out / "cas_pairwise_degeneracy.md").read_text(encoding="utf-8")
    con = connect(state["db_path"])
    pid = upsert_problem(con, state["problem"])
    insert_computation(con, pid, state["run_id"], state["iteration"], "cas_pairwise_degeneracy", md, code_path="src/math_workbench/tools/cas.py", data_path=str(out), report_path=str(out / "cas_pairwise_degeneracy.md"))
    con.close()
    return {"cas_report": md}


def node_formalization(state: WorkbenchState) -> dict[str, Any]:
    # Ask LLM for possible small Lean tasks; then run starter checks.
    proof_text = "\n\n".join([r["report"] for r in state.get("strategy_reports", [])])
    raw = llm_call(FORMAL_TASK_TEMPLATE.format(proof_text=proof_text[:12000]))
    write_iter_file(state, "formal_task_generation_raw.md", raw)
    formal_dir = Path(state["out_dir"]) / "formal" / f"it{state['iteration']:02d}"
    lean_res = run_local_lean(str(formal_dir))
    aristotle_res = run_aristotle_cli(str(formal_dir)) if os.environ.get("RUN_ARISTOTLE", "0") == "1" else {"ok": False, "backend": "ARISTOTLE_CLI", "error": "RUN_ARISTOTLE not enabled"}
    report = "# Formalization report\n\n## Suggested tasks\n\n" + raw + "\n\n## Local Lean\n\n```json\n" + json.dumps(lean_res, indent=2)[:8000] + "\n```\n\n## Aristotle\n\n```json\n" + json.dumps(aristotle_res, indent=2)[:8000] + "\n```\n"
    write_iter_file(state, "formalization_report.md", report)
    return {"formalization_report": report}


def node_synthesize(state: WorkbenchState) -> dict[str, Any]:
    prompt = SYNTHESIS_TEMPLATE.format(
        problem_summary=problem_summary(state["problem"]),
        frontier=state["current_frontier"],
        selected_report=state.get("selected_report", ""),
        strategy_reports=json.dumps([{ "strategy": r["strategy"], "report": r["report"][:6000] } for r in state.get("strategy_reports", [])], indent=2),
        symbolic_report=state.get("symbolic_report", ""),
        cas_report=state.get("cas_report", "")[:8000],
        formalization_report=state.get("formalization_report", "")[:8000],
        discovery_report=state.get("discovery_report", ""),
    )
    result = llm_call(prompt)
    write_iter_file(state, "synthesis.md", result)
    resolved = ("full project is resolved" in result.lower() or "project is resolved" in result.lower()) and "FAILED/OPEN" not in result
    remaining = extract_remaining(result)
    con = connect(state["db_path"])
    pid = upsert_problem(con, state["problem"])
    insert_theorem(con, pid, "current-frontier", "Current sharpest remaining theorem", remaining, "FAILED/OPEN", 1)
    con.close()
    return {"synthesis": result, "sharpest_remaining_theorem": remaining, "resolved": resolved, "current_frontier": remaining or state["current_frontier"]}


def extract_remaining(text: str) -> str:
    keys = ["Sharpest remaining theorem", "exact next theorem", "current exact frontier", "remaining theorem", "true obstruction"]
    lower = text.lower()
    for k in keys:
        i = lower.find(k.lower())
        if i >= 0:
            return text[i:i+2500]
    return text[-2500:]


def node_discover(state: WorkbenchState) -> dict[str, Any]:
    prompt = DISCOVERY_TEMPLATE.format(
        problem_summary=problem_summary(state["problem"]),
        frontier=state["current_frontier"],
        synthesis=state.get("synthesis", "")[:12000],
    )
    result = llm_call(prompt)
    write_iter_file(state, "strategy_discovery_report.md", result)
    # Conservative: do not auto-append new strategies unless user edits YAML.
    return {"discovery_report": result}


def should_continue(state: WorkbenchState) -> Literal["continue", "end"]:
    if state.get("resolved", False):
        return "end"
    if state["iteration"] + 1 >= state["max_iterations"]:
        return "end"
    return "continue"


def node_increment(state: WorkbenchState) -> dict[str, Any]:
    return {"iteration": state["iteration"] + 1}


def build_graph():
    g = StateGraph(WorkbenchState)
    g.add_node("select_strategies", node_select_strategies)
    g.add_node("run_strategies", node_run_strategies)
    g.add_node("symbolic_checks", node_symbolic_checks)
    g.add_node("cas_degeneracy", node_cas_degeneracy)
    g.add_node("formalization", node_formalization)
    g.add_node("synthesize", node_synthesize)
    g.add_node("discover", node_discover)
    g.add_node("increment", node_increment)

    g.add_edge(START, "select_strategies")
    g.add_edge("select_strategies", "run_strategies")
    g.add_edge("run_strategies", "symbolic_checks")
    g.add_edge("symbolic_checks", "cas_degeneracy")
    g.add_edge("cas_degeneracy", "formalization")
    g.add_edge("formalization", "synthesize")
    g.add_edge("synthesize", "discover")
    g.add_conditional_edges("discover", should_continue, {"continue": "increment", "end": END})
    g.add_edge("increment", "select_strategies")
    return g.compile(checkpointer=InMemorySaver())


def run(problem_path: str, strategies_path: str, iterations: int, parallel_strategies: int, out: str, db: str) -> dict[str, Any]:
    problem = ProblemSpec.from_yaml(problem_path)
    portfolio = StrategyPortfolio.from_yaml(strategies_path)
    Path(out).mkdir(parents=True, exist_ok=True)
    init_db(db)
    con = connect(db)
    upsert_problem(con, problem.__dict__)
    for s in portfolio.strategies:
        upsert_strategy(con, s.__dict__)
    con.close()

    state: WorkbenchState = {
        "run_id": str(uuid.uuid4()),
        "out_dir": out,
        "db_path": db,
        "iteration": 0,
        "max_iterations": iterations,
        "parallel_strategies": parallel_strategies,
        "problem": problem.__dict__,
        "strategies": [s.__dict__ for s in portfolio.strategies],
        "active_strategies": [],
        "proof_ledger": [],
        "failed_strategies": [],
        "computations": [],
        "formalizations": [],
        "current_frontier": problem.current_frontier,
        "sharpest_remaining_theorem": problem.current_frontier,
        "selected_report": "",
        "strategy_reports": [],
        "symbolic_report": "",
        "cas_report": "",
        "formalization_report": "",
        "synthesis": "",
        "discovery_report": "",
        "resolved": False,
    }
    app = build_graph()
    final = app.invoke(state, config={"configurable": {"thread_id": state["run_id"]}})
    Path(out, "final_state.json").write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8")
    return final


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem", required=True)
    parser.add_argument("--strategies", required=True)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--parallel-strategies", type=int, default=3)
    parser.add_argument("--out", default="runs/run")
    parser.add_argument("--db", default="proof_codex.sqlite")
    parser.add_argument("--settings", default="config/local_settings.yaml", help="Path to local settings YAML with model/API key")
    args = parser.parse_args()
    os.environ["MATH_WORKBENCH_CONFIG"] = args.settings
    final = run(args.problem, args.strategies, args.iterations, args.parallel_strategies, args.out, args.db)
    print(final.get("synthesis", ""))


if __name__ == "__main__":
    import argparse
    main()
