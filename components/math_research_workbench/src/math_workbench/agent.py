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

from .conjecture import Conjecture, ConjectureError, load_conjectures
from .config import ProblemSpec, StrategyPortfolio, load_app_config
from .prompts import (
    SYSTEM_PROMPT,
    SELECT_STRATEGIES_TEMPLATE,
    STRATEGY_LANE_TEMPLATE,
    REFUTE_LANE_TEMPLATE,
    REPAIR_TEMPLATE,
    SYNTHESIS_TEMPLATE,
    DISCOVERY_TEMPLATE,
    FORMAL_TASK_TEMPLATE,
    WITNESS_FORMAT,
)
from .state import WorkbenchState
from .tools.cas import symbolic_core_checks, cas_pairwise_degeneracy
from .tools.codex import (
    connect,
    init_db,
    upsert_problem,
    upsert_strategy,
    insert_attempt,
    insert_computation,
    insert_theorem,
    insert_counterexample,
    insert_falsification,
    record_search_outcome,
    upsert_conjecture,
)
from .tools.formalization import run_local_lean, run_aristotle_cli
from .tools.refutation import (
    check_claimed_witnesses,
    render_report,
    search_conjectures,
    CONTESTED,
    SOURCE_LLM,
    STATUS_CONTESTED,
    STATUS_FALSIFIED,
    STATUS_VERIFIED_EXHAUSTIVE,
)


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


def build_conjectures(state: WorkbenchState) -> tuple[list[Conjecture], list[str]]:
    """Parse declared conjectures, reporting bad ones instead of aborting the run.

    A malformed predicate in one conjecture must not take down the whole
    iteration -- the other conjectures are still searchable, and the error is
    more useful surfaced in the report than as a traceback.
    """
    conjectures: list[Conjecture] = []
    errors: list[str] = []
    for spec in state["problem"].get("conjectures", []) or []:
        try:
            conjectures.append(Conjecture.from_dict(spec))
        except ConjectureError as exc:
            errors.append(f"{spec.get('id', '<unnamed>')}: {exc}")
    return conjectures, errors


def conjecture_summary(conjectures: list[Conjecture]) -> str:
    if not conjectures:
        return "(none declared -- refutation is limited to model-proposed witnesses)"
    lines = []
    for c in conjectures:
        domains = "; ".join(d.describe() for d in c.variables.values())
        lines.append(f"- {c.id}: {c.statement}")
        lines.append(f"    predicate: {c.predicate}")
        lines.append(f"    over: {domains} ({c.space_size()} points)")
        if c.assumptions:
            lines.append(f"    assuming: {', '.join(c.assumptions)}")
    return "\n".join(lines)


def node_select_strategies(state: WorkbenchState) -> dict[str, Any]:
    """Reserve refutation lanes before proof lanes compete for the budget.

    Ranking alone would let proof lanes crowd out refutation entirely, which is
    how the old pipeline ended up never falsifying anything. The two pools are
    filled separately.
    """
    strategies = sorted(state["strategies"], key=lambda s: (s.get("rank", 100), -s.get("score", 0)))
    live = [s for s in strategies if str(s.get("status", "ACTIVE")).upper() != "DEMOTED"]
    provers = [s for s in live if str(s.get("mode", "PROVE")).upper() in {"PROVE", "BOTH"}]
    refuters = [s for s in live if str(s.get("mode", "PROVE")).upper() in {"REFUTE", "BOTH"}]

    active = provers[: state["parallel_strategies"]]
    active_refuters = refuters[: state["parallel_refutations"]]

    conjectures, _errors = build_conjectures(state)
    prompt = SELECT_STRATEGIES_TEMPLATE.format(
        problem_summary=problem_summary(state["problem"]),
        frontier=state["current_frontier"],
        conjectures=conjecture_summary(conjectures),
        refutation_summary=state.get("refutation_report", "")[:4000] or "(nothing yet -- first iteration)",
        strategies=json.dumps(strategies, indent=2),
        k=state["parallel_strategies"],
        k_refute=state["parallel_refutations"],
    )
    result = llm_call(prompt)
    write_iter_file(state, "selected_strategies.md", result)
    return {"active_strategies": active, "active_refuters": active_refuters, "selected_report": result}


def node_search_counterexamples(state: WorkbenchState) -> dict[str, Any]:
    """Sweep every declared conjecture for witnesses. No model in the loop.

    This runs before the proof lanes, so a statement that dies here never costs
    a proof budget. It is also fully deterministic, which means a refutation
    found by this node is reproducible from the problem spec alone.
    """
    conjectures, errors = build_conjectures(state)
    cfg = load_app_config()
    budget = cfg.search_budget(state["problem"].get("refutation", {}))

    outcomes = search_conjectures(conjectures, budget)

    con = connect(state["db_path"])
    problem_id = upsert_problem(con, state["problem"])
    for conjecture, outcome in zip(conjectures, outcomes):
        record_search_outcome(
            con,
            problem_id,
            conjecture,
            outcome,
            run_id=state["run_id"],
            iteration=state["iteration"],
        )
    for message in errors:
        insert_falsification(
            con,
            problem_id,
            obstruction=f"Malformed conjecture specification: {message}",
            severity="LOW",
            run_id=state["run_id"],
            iteration=state["iteration"],
        )
    con.close()

    report = render_report(outcomes)
    if errors:
        report += "\n## Malformed conjecture specifications\n\n" + "\n".join(f"- {e}" for e in errors) + "\n"
    write_iter_file(state, "counterexample_search.md", report)
    return {
        "conjectures": [
            {"id": c.id, "statement": c.statement, "predicate": c.predicate} for c in conjectures
        ],
        "search_outcomes": [o.as_dict() for o in outcomes],
    }


def node_refute_lanes(state: WorkbenchState) -> dict[str, Any]:
    """Run the refutation strategies and check every witness they claim.

    A lane's prose is advisory; only its witness blocks are actionable, and each
    one is re-evaluated here before it can reach the ledger.
    """
    conjectures, _errors = build_conjectures(state)
    search_summary = summarise_outcome_dicts(state.get("search_outcomes", []))
    discarded_so_far = state.get("discarded_witnesses", [])
    discarded_text = (
        "\n".join(f"- {w['conjecture_id']}: {w['assignment']} ({w['detail']})" for w in discarded_so_far[-20:])
        or "(none yet)"
    )

    con = connect(state["db_path"])
    problem_id = upsert_problem(con, state["problem"])
    strategy_id_map = {s["id"]: upsert_strategy(con, s) for s in state["strategies"]}
    conjecture_ids = {c.id: upsert_conjecture(con, problem_id, c) for c in conjectures}

    reports: list[dict[str, str]] = []
    checked: list[dict[str, Any]] = []
    for strategy in state.get("active_refuters", []):
        allowed = strategy.get("target_conjectures") or []
        lane_conjectures = [c for c in conjectures if not allowed or c.id in allowed]
        prompt = REFUTE_LANE_TEMPLATE.format(
            problem_summary=problem_summary(state["problem"]),
            frontier=state["current_frontier"],
            id=strategy["id"],
            name=strategy.get("name", strategy["id"]),
            description=strategy.get("description", ""),
            conjectures=conjecture_summary(lane_conjectures),
            search_summary=search_summary,
            discarded=discarded_text,
            counterexample_prompts="\n".join(
                f"- {x}"
                for x in (strategy.get("counterexample_prompts") or strategy.get("falsification_prompts") or [])
            )
            or "- (none configured; use your own judgement)",
            failure_modes="\n".join(f"- {x}" for x in strategy.get("failure_modes", [])) or "- (none configured)",
            witness_format=WITNESS_FORMAT,
        )
        result = llm_call(prompt)
        path = write_iter_file(state, f"refutation_{strategy['id']}.md", result)

        witnesses = check_claimed_witnesses(lane_conjectures, result, source=SOURCE_LLM)
        survivors = [w for w in witnesses if w.refutes()]
        insert_attempt(
            con,
            problem_id,
            state["run_id"],
            state["iteration"],
            strategy_id_map.get(strategy["id"]),
            prompt,
            result,
            status="FALSIFIED" if survivors else "FAILED/OPEN",
        )
        for witness in witnesses:
            insert_counterexample(
                con,
                problem_id,
                conjecture_ids.get(witness.conjecture_id),
                witness,
                run_id=state["run_id"],
                iteration=state["iteration"],
                strategy_id=strategy_id_map.get(strategy["id"]),
            )
        checked.extend(w.as_dict() for w in witnesses)
        reports.append(
            {
                "strategy": strategy["id"],
                "path": path,
                "report": result,
                "claimed": str(len(witnesses)),
                "survived": str(len(survivors)),
            }
        )
    con.close()

    if reports:
        batch = "\n\n".join(f"# {r['strategy']}\n\n{r['report']}" for r in reports)
        write_iter_file(state, "refutation_batch_report.md", batch)
    return {"refutation_reports": reports, "claimed_witnesses": checked}


def summarise_outcome_dicts(outcomes: list[dict[str, Any]]) -> str:
    """Compact digest of the automated sweep, for feeding back into a prompt."""
    if not outcomes:
        return "no executable conjectures were declared, so nothing was swept"
    lines = []
    for outcome in outcomes:
        head = f"{outcome['conjecture_id']}: {outcome['status']}"
        witnesses = outcome.get("witnesses") or []
        if witnesses:
            shown = "; ".join(
                ", ".join(f"{k} = {v}" for k, v in w["assignment"].items()) for w in witnesses[:3]
            )
            head += f" -- witnesses at {shown}"
        elif outcome["status"] == STATUS_VERIFIED_EXHAUSTIVE:
            head += f" -- no counterexample in all {outcome['space_size']} points of the declared space"
        else:
            head += (
                f" -- {outcome['evaluated']} of {outcome['space_size']} points searched, none refuted it"
            )
        lines.append(head)
    return "\n".join(lines)


def node_assess_refutation(state: WorkbenchState) -> dict[str, Any]:
    """Consolidate both refutation sources and decide whether the frontier died.

    This is the only place that promotes a witness to "verified". It also marks
    the corresponding theorem FALSIFIED in the ledger, so the proof track cannot
    keep working on a statement the refutation track has already killed.
    """
    verified: list[dict[str, Any]] = []
    contested: list[dict[str, Any]] = []
    discarded: list[dict[str, Any]] = list(state.get("discarded_witnesses", []))
    falsified: list[str] = []
    exhausted: list[str] = []

    for outcome in state.get("search_outcomes", []):
        if outcome["status"] == STATUS_CONTESTED:
            # The search disagreed with itself. Its witnesses are withheld along
            # with the disagreement rather than promoted -- an evaluator that is
            # wrong somewhere is not a source of verified refutations anywhere.
            contested.extend(outcome.get("contested") or [])
            contested.extend(outcome.get("witnesses") or [])
            continue
        if outcome["status"] == STATUS_FALSIFIED:
            falsified.append(outcome["conjecture_id"])
        elif outcome["status"] == STATUS_VERIFIED_EXHAUSTIVE:
            exhausted.append(outcome["conjecture_id"])
        verified.extend(outcome.get("witnesses") or [])

    for witness in state.get("claimed_witnesses", []):
        if witness["verification"] in {"VERIFIED_EXACT", "VERIFIED_SINGLE"}:
            verified.append(witness)
            if witness["conjecture_id"] not in falsified:
                falsified.append(witness["conjecture_id"])
        elif witness["verification"] == CONTESTED:
            contested.append(witness)
        else:
            discarded.append(witness)

    previously = set(state.get("falsified_conjectures", []))
    newly_falsified = [c for c in falsified if c not in previously]

    conjectures, _errors = build_conjectures(state)
    by_id = {c.id: c for c in conjectures}

    # Record the kill in the theorem ledger, so a FALSIFIED conjecture shows up
    # next to the theorems rather than only in a side table.
    con = connect(state["db_path"])
    problem_id = upsert_problem(con, state["problem"])
    for cid in newly_falsified:
        conjecture = by_id.get(cid)
        witnesses = [w for w in verified if w["conjecture_id"] == cid]
        witness_text = "; ".join(
            ", ".join(f"{k} = {v}" for k, v in w["assignment"].items()) for w in witnesses[:5]
        )
        insert_theorem(
            con,
            problem_id,
            slug=f"falsified-{cid}",
            title=f"FALSIFIED: {cid}",
            statement=(conjecture.statement if conjecture else cid)
            + f"\n\nRefuted by verified counterexample(s): {witness_text}",
            status="FALSIFIED",
            frontier_rank=0,
        )
    con.close()

    exhausted_only = [c for c in exhausted if c not in falsified]
    report_parts = [
        "# Refutation assessment",
        "",
        f"- conjectures falsified this run: {len(falsified)}"
        + (f" ({', '.join(falsified)})" if falsified else ""),
        f"- newly falsified this iteration: {len(newly_falsified)}"
        + (f" ({', '.join(newly_falsified)})" if newly_falsified else ""),
        f"- verified exhaustively over their declared space: {len(exhausted_only)}"
        + (f" ({', '.join(exhausted_only)})" if exhausted_only else ""),
        f"- verified witnesses on record: {len(verified)}",
        f"- witnesses discarded on checking: {len(discarded)}",
        f"- CONTESTED witnesses (evaluator disagreement -- investigate): {len(contested)}",
        "",
    ]
    if contested:
        report_parts += [
            "## Contested witnesses",
            "",
            "The rational and symbolic evaluators disagreed on these assignments.",
            "That is a bug in one of them. No refutation below depends on them.",
            "",
        ]
        report_parts += [
            f"- {w['conjecture_id']} at " + ", ".join(f"{k} = {v}" for k, v in w["assignment"].items())
            for w in contested
        ]
        report_parts.append("")
    if verified:
        report_parts += ["## Verified counterexamples", ""]
        for w in verified:
            assignment = ", ".join(f"{k} = {v}" for k, v in w["assignment"].items())
            report_parts.append(f"- {w['conjecture_id']} at {assignment} [{w['verification']}, {w['source']}]")
        report_parts.append("")
    if discarded:
        report_parts += [
            "## Discarded claims",
            "",
            f"{len(discarded)} proposed witness(es) did not survive independent checking:",
            "",
        ]
        report_parts += [
            f"- {w['conjecture_id']} at "
            + ", ".join(f"{k} = {v}" for k, v in w["assignment"].items())
            + f" -- {w['detail']}"
            for w in discarded[-20:]
        ]
        report_parts.append("")

    report = "\n".join(report_parts)
    write_iter_file(state, "refutation_assessment.md", report)

    return {
        "verified_counterexamples": verified,
        "contested_witnesses": contested,
        "discarded_witnesses": discarded,
        "falsified_conjectures": falsified,
        "exhaustively_verified": exhausted_only,
        "refutation_report": report,
        "frontier_falsified": bool(newly_falsified),
    }


def node_repair(state: WorkbenchState) -> dict[str, Any]:
    """Turn a counterexample into the next statement worth attacking.

    Without this the pipeline would treat a refutation as a dead end. The repair
    becomes the new frontier, so falsification advances the run instead of
    ending it.
    """
    falsified = state.get("falsified_conjectures", [])
    conjectures, _errors = build_conjectures(state)
    by_id = {c.id: c for c in conjectures}
    statements = [
        f"{cid}: {by_id[cid].statement if cid in by_id else '(statement unavailable)'}" for cid in falsified
    ]
    witnesses = [
        f"- {w['conjecture_id']} at " + ", ".join(f"{k} = {v}" for k, v in w["assignment"].items())
        + f" [{w['verification']}]"
        for w in state.get("verified_counterexamples", [])
    ]
    prompt = REPAIR_TEMPLATE.format(
        problem_summary=problem_summary(state["problem"]),
        falsified_statement="\n".join(statements) or state["current_frontier"],
        witnesses="\n".join(witnesses) or "(none)",
        refutation_summary=state.get("refutation_report", "")[:8000],
    )
    result = llm_call(prompt)
    write_iter_file(state, "repair.md", result)

    con = connect(state["db_path"])
    problem_id = upsert_problem(con, state["problem"])
    insert_theorem(
        con,
        problem_id,
        slug="repaired-frontier",
        title="Repaired frontier after falsification",
        statement=result[:8000],
        status="FAILED/OPEN",
        frontier_rank=1,
    )
    con.close()
    return {"repair_report": result, "current_frontier": extract_remaining(result) or state["current_frontier"]}


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
            refutation_summary=state.get("refutation_report", "")[:4000]
            or "(the refutation track found nothing this iteration)",
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
        refutation_report=state.get("refutation_report", "")[:8000],
        repair_report=state.get("repair_report", "")[:6000] or "(nothing was falsified, so no repair was needed)",
        discovery_report=state.get("discovery_report", ""),
    )
    result = llm_call(prompt)
    write_iter_file(state, "synthesis.md", result)
    lower = result.lower()

    # A run can now end two ways. "Resolved negatively" means the target itself
    # was refuted -- that is a finished project, not a failed one, and it is only
    # claimed when a verified witness actually exists to back it up.
    resolved_negatively = "resolved negatively" in lower and bool(state.get("verified_counterexamples"))
    resolved_positively = (
        ("full project is resolved" in lower or "project is resolved" in lower)
        and "resolved negatively" not in lower
        and "FAILED/OPEN" not in result
    )
    resolution = "PROVED" if resolved_positively else "FALSIFIED" if resolved_negatively else "OPEN"

    remaining = extract_remaining(result)
    con = connect(state["db_path"])
    pid = upsert_problem(con, state["problem"])
    insert_theorem(
        con,
        pid,
        "current-frontier",
        "Current sharpest remaining theorem",
        remaining,
        "FALSIFIED" if resolved_negatively else "FAILED/OPEN",
        1,
    )
    con.close()
    return {
        "synthesis": result,
        "sharpest_remaining_theorem": remaining,
        "resolved": resolved_positively or resolved_negatively,
        "resolution": resolution,
        "current_frontier": remaining or state["current_frontier"],
    }


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
        refutation_report=state.get("refutation_report", "")[:6000],
    )
    result = llm_call(prompt)
    write_iter_file(state, "strategy_discovery_report.md", result)
    # Conservative: do not auto-append new strategies or conjectures unless the
    # user edits the YAML. A model-proposed predicate is executable code.
    return {"discovery_report": result}


def route_after_refutation(state: WorkbenchState) -> Literal["repair", "prove"]:
    """Skip the proof lanes for an iteration whose frontier just died.

    Proving a statement that has a verified counterexample is the single most
    expensive thing this pipeline can do, so the repair runs first and the next
    iteration's proof lanes get the repaired statement instead.
    """
    return "repair" if state.get("frontier_falsified", False) else "prove"


def should_continue(state: WorkbenchState) -> Literal["continue", "end"]:
    if state.get("resolved", False):
        return "end"
    if state["iteration"] + 1 >= state["max_iterations"]:
        return "end"
    return "continue"


def node_increment(state: WorkbenchState) -> dict[str, Any]:
    return {"iteration": state["iteration"] + 1}


def build_graph():
    """Refutation runs before proof, and can divert the iteration.

        select_strategies
          -> search_counterexamples      (deterministic sweep, no model)
          -> refute_lanes                (model-proposed witnesses, each checked)
          -> assess_refutation
               |-- frontier falsified --> repair ------------> synthesize
               `-- survived ------------> run_strategies
                                          -> symbolic_checks
                                          -> cas_degeneracy
                                          -> formalization ---> synthesize
          -> discover -> repeat

    The old graph ran proof lanes first and had no refutation stage at all.
    """
    g = StateGraph(WorkbenchState)
    g.add_node("select_strategies", node_select_strategies)
    g.add_node("search_counterexamples", node_search_counterexamples)
    g.add_node("refute_lanes", node_refute_lanes)
    g.add_node("assess_refutation", node_assess_refutation)
    g.add_node("repair", node_repair)
    g.add_node("run_strategies", node_run_strategies)
    g.add_node("symbolic_checks", node_symbolic_checks)
    g.add_node("cas_degeneracy", node_cas_degeneracy)
    g.add_node("formalization", node_formalization)
    g.add_node("synthesize", node_synthesize)
    g.add_node("discover", node_discover)
    g.add_node("increment", node_increment)

    g.add_edge(START, "select_strategies")
    g.add_edge("select_strategies", "search_counterexamples")
    g.add_edge("search_counterexamples", "refute_lanes")
    g.add_edge("refute_lanes", "assess_refutation")
    g.add_conditional_edges(
        "assess_refutation", route_after_refutation, {"repair": "repair", "prove": "run_strategies"}
    )
    g.add_edge("repair", "synthesize")
    g.add_edge("run_strategies", "symbolic_checks")
    g.add_edge("symbolic_checks", "cas_degeneracy")
    g.add_edge("cas_degeneracy", "formalization")
    g.add_edge("formalization", "synthesize")
    g.add_edge("synthesize", "discover")
    g.add_conditional_edges("discover", should_continue, {"continue": "increment", "end": END})
    g.add_edge("increment", "select_strategies")
    return g.compile(checkpointer=InMemorySaver())


def initial_state(
    problem: ProblemSpec,
    portfolio: StrategyPortfolio,
    *,
    run_id: str,
    out: str,
    db: str,
    iterations: int,
    parallel_strategies: int,
    parallel_refutations: int,
) -> WorkbenchState:
    """The starting state, split out so tests can build one without a model."""
    return {
        "run_id": run_id,
        "out_dir": out,
        "db_path": db,
        "iteration": 0,
        "max_iterations": iterations,
        "parallel_strategies": parallel_strategies,
        "parallel_refutations": parallel_refutations,
        "problem": problem.__dict__,
        "strategies": [s.__dict__ for s in portfolio.strategies],
        "active_strategies": [],
        "active_refuters": [],
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
        "conjectures": [],
        "search_outcomes": [],
        "claimed_witnesses": [],
        "verified_counterexamples": [],
        "contested_witnesses": [],
        "discarded_witnesses": [],
        "falsified_conjectures": [],
        "exhaustively_verified": [],
        "refutation_reports": [],
        "refutation_report": "",
        "repair_report": "",
        "frontier_falsified": False,
        "resolution": "OPEN",
    }


def run(
    problem_path: str,
    strategies_path: str,
    iterations: int,
    parallel_strategies: int,
    out: str,
    db: str,
    parallel_refutations: int = 1,
) -> dict[str, Any]:
    problem = ProblemSpec.from_yaml(problem_path)
    portfolio = StrategyPortfolio.from_yaml(strategies_path)
    Path(out).mkdir(parents=True, exist_ok=True)
    report = init_db(db)
    if not report.already_current:
        print(f"[codex] {report.summary()}")

    # Fail before spending a model call: a conjecture with a bad predicate should
    # be a startup error, not a surprise three iterations in.
    conjectures = load_conjectures(problem.conjectures)

    con = connect(db)
    problem_id = upsert_problem(con, problem.__dict__)
    for s in portfolio.strategies:
        upsert_strategy(con, s.__dict__)
    for c in conjectures:
        upsert_conjecture(con, problem_id, c)
    con.close()

    state = initial_state(
        problem,
        portfolio,
        run_id=str(uuid.uuid4()),
        out=out,
        db=db,
        iterations=iterations,
        parallel_strategies=parallel_strategies,
        parallel_refutations=parallel_refutations,
    )
    app = build_graph()
    final = app.invoke(state, config={"configurable": {"thread_id": state["run_id"]}})
    Path(out, "final_state.json").write_text(json.dumps(final, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return final


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem", required=True)
    parser.add_argument("--strategies")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--parallel-strategies", type=int, default=3)
    parser.add_argument(
        "--parallel-refutations",
        type=int,
        default=1,
        help="Refutation lanes reserved per iteration. Set 0 to disable the model-driven "
        "refutation lanes; the deterministic sweep still runs.",
    )
    parser.add_argument("--out", default="runs/run")
    parser.add_argument("--db", default="proof_codex.sqlite")
    parser.add_argument("--settings", default="config/local_settings.yaml", help="Path to local settings YAML with model/API key")
    parser.add_argument(
        "--sweep-only",
        action="store_true",
        help="Run the counterexample sweep and exit. No model calls, no API key needed.",
    )
    args = parser.parse_args()
    os.environ["MATH_WORKBENCH_CONFIG"] = args.settings

    if args.sweep_only:
        from .sweep import sweep

        result = sweep(args.problem, db=args.db, out=str(Path(args.out) / "counterexample_search.md"))
        raise SystemExit(1 if result["falsified"] else 0)

    if not args.strategies:
        parser.error("--strategies is required unless --sweep-only is given")
    final = run(
        args.problem,
        args.strategies,
        args.iterations,
        args.parallel_strategies,
        args.out,
        args.db,
        parallel_refutations=args.parallel_refutations,
    )
    print(final.get("synthesis", ""))


if __name__ == "__main__":
    import argparse
    main()
