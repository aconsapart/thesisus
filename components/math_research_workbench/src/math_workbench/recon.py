"""Prior-art recon, runnable without a model.

The search itself needs a model with retrieval, but the two useful halves around
it do not, and both are worth having on their own:

    # 1. emit the hostile-search prompts, to paste into whatever session has
    #    the better literature access
    python -m math_workbench.recon --problem p.yaml --emit-prompts

    # 2. grade what came back: union the passes, apply the discipline rules,
    #    and say which claims survive
    python -m math_workbench.recon --problem p.yaml --ingest pass1.md pass2.md

Splitting it this way means the search can happen anywhere -- a different model,
a librarian, a colleague -- while the standard applied to the result stays the
same and stays in version control.

Exit codes:
    0  every claim CLEAR
    1  at least one claim KILLED or WOUNDED (the search did its job)
    2  at least one claim UNDER_SEARCHED, and nothing worse (search again)
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Sequence

from .config import ProblemSpec
from .prior_art import (
    ANGLES,
    STATUS_CLEAR,
    STATUS_KILLED,
    STATUS_UNDER_SEARCHED,
    STATUS_WOUNDED,
    Claim,
    PriorArtPolicy,
    SearchPass,
)
from .prompts import (
    ANGLE_GUIDANCE,
    HOSTILE_SEARCH_TEMPLATE,
    RECON_BLOCK_FORMAT,
)
from .tools.recon import merge_passes, parse_search_pass, render_claims_file, render_report

__all__ = ["emit_prompts", "ingest", "claims_summary", "main"]


def claims_summary(claims: Sequence[Claim]) -> str:
    if not claims:
        return "(none declared)"
    lines = []
    for c in claims:
        lines.append(f"- {c.id} [{c.kind}]: {c.statement}")
        if c.novelty_basis:
            lines.append(f"    asserted to be new because: {c.novelty_basis}")
        if c.search_terms:
            lines.append(f"    suggested terms: {', '.join(c.search_terms)}")
        if c.adjacent_fields:
            lines.append(f"    adjacent fields: {', '.join(c.adjacent_fields)}")
        overclaims = c.overclaims()
        if overclaims:
            lines.append(
                "    NOTE: this statement uses priority language "
                f"({'; '.join(str(o) for o in overclaims)}) -- it must come back CLEAR or be rewritten"
            )
    return "\n".join(lines)


def _conceded(claims: Sequence[Claim]) -> str:
    known = [f"- {c.id}: {art}" for c in claims for art in c.known_prior_art]
    if not known:
        return (
            "(none conceded -- which is itself suspicious. A search that starts from "
            "zero known prior art usually means the authors have not looked yet.)"
        )
    return "\n".join(known)


def emit_prompts(
    problem_path: str,
    angles: Sequence[str] = ANGLES,
    out_dir: str | None = None,
    previous: str = "",
) -> dict[str, str]:
    """One hostile-search prompt per angle.

    Separate prompts rather than one combined prompt on purpose: a single
    request to "search thoroughly" collapses into one phrasing and one
    literature, which is the failure mode the angle rule exists to prevent.
    """
    problem = ProblemSpec.from_yaml(problem_path)
    claims = problem.build_claims()
    if not claims:
        raise SystemExit(
            f"{problem_path} declares no `claims:` block. Nothing to search for.\n"
            "A claim is a separately attackable contribution -- see "
            "docs/PRIOR_ART.md for the format."
        )

    summary = f"{problem.title}\n\n{problem.background}".strip()
    prompts: dict[str, str] = {}
    for angle in angles:
        angle = angle.upper()
        prompts[angle] = HOSTILE_SEARCH_TEMPLATE.format(
            problem_summary=summary,
            claims=claims_summary(claims),
            conceded=_conceded(claims),
            previous_findings=previous or "(this is the first pass; nothing found yet)",
            angle=angle,
            angle_guidance=ANGLE_GUIDANCE.get(angle, ""),
            phrasing=(
                f"use vocabulary you have NOT used in another pass; this pass is "
                f"identified as `{angle.lower()}` and its blocks must carry that pass id"
            ),
            block_format=RECON_BLOCK_FORMAT,
        )
    if out_dir:
        directory = Path(out_dir)
        directory.mkdir(parents=True, exist_ok=True)
        for angle, text in prompts.items():
            (directory / f"hostile_search_{angle.lower()}.md").write_text(text, encoding="utf-8")
    return prompts


def ingest(
    problem_path: str,
    responses: Sequence[str],
    db: str | None = None,
    out: str | None = None,
    claims_out: str | None = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """Grade a set of search-pass responses against the policy."""
    problem = ProblemSpec.from_yaml(problem_path)
    claims = problem.build_claims()
    policy = problem.prior_art_policy()

    passes: list[SearchPass] = []
    problems: list[str] = []
    for index, path in enumerate(responses, start=1):
        text = Path(path).read_text(encoding="utf-8")
        pass_id = Path(path).stem or f"pass{index}"
        sweep, issues = parse_search_pass(text, claims, pass_id=pass_id, phrasing=pass_id)
        passes.append(sweep)
        problems.extend(f"{pass_id}: {issue}" for issue in issues)

    assessments = merge_passes(claims, passes, policy)
    report = render_report(assessments, passes, problems)
    claims_file = render_claims_file(assessments)

    if not quiet:
        print(report)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(report, encoding="utf-8")
    if claims_out:
        Path(claims_out).parent.mkdir(parents=True, exist_ok=True)
        Path(claims_out).write_text(claims_file, encoding="utf-8")
    if db:
        from .tools.codex import connect, init_db, insert_search_pass, record_claim_assessment, upsert_problem

        init_db(db)
        con = connect(db)
        problem_id = upsert_problem(con, problem.__dict__)
        pass_ids = {
            sweep.id: insert_search_pass(con, problem_id, sweep, run_id="recon", iteration=0)
            for sweep in passes
        }
        for assessment in assessments:
            record_claim_assessment(con, problem_id, assessment, pass_ids=pass_ids)
        con.close()

    return {
        "problem": problem.slug,
        "assessments": [a.as_dict() for a in assessments],
        "killed": [a.claim_id for a in assessments if a.status == STATUS_KILLED],
        "wounded": [a.claim_id for a in assessments if a.status == STATUS_WOUNDED],
        "under_searched": [a.claim_id for a in assessments if a.status == STATUS_UNDER_SEARCHED],
        "clear": [a.claim_id for a in assessments if a.status == STATUS_CLEAR],
        "report": report,
        "claims_file": claims_file,
        "parse_problems": problems,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--problem", required=True)
    parser.add_argument(
        "--emit-prompts",
        action="store_true",
        help="Print the hostile-search prompts, one per angle, and exit.",
    )
    parser.add_argument(
        "--ingest",
        nargs="+",
        metavar="RESPONSE",
        help="Files holding search-pass responses to grade. Give at least two.",
    )
    parser.add_argument("--angles", nargs="+", default=list(ANGLES), help="Angles to emit prompts for.")
    parser.add_argument("--prompt-dir", default=None, help="Also write emitted prompts here.")
    parser.add_argument("--db", default=None, help="Persist the threat table to this codex.")
    parser.add_argument("--out", default=None, help="Write the threat-table report here.")
    parser.add_argument("--claims-out", default=None, help="Write the defensible claim set here.")
    args = parser.parse_args()

    if args.emit_prompts:
        prompts = emit_prompts(args.problem, angles=args.angles, out_dir=args.prompt_dir)
        for angle, text in prompts.items():
            print(f"\n{'=' * 72}\n=== SEARCH PASS: {angle}\n{'=' * 72}\n")
            print(text)
        if args.prompt_dir:
            print(f"\n[written to {args.prompt_dir}]")
        print(
            f"\nRun at least {PriorArtPolicy().min_passes} of these in separate sessions, "
            "then grade them together:\n"
            f"  python -m math_workbench.recon --problem {args.problem} --ingest pass1.md pass2.md"
        )
        raise SystemExit(0)

    if not args.ingest:
        parser.error("give either --emit-prompts or --ingest")

    result = ingest(
        args.problem,
        args.ingest,
        db=args.db,
        out=args.out,
        claims_out=args.claims_out,
    )
    if result["killed"] or result["wounded"]:
        raise SystemExit(1)
    if result["under_searched"]:
        print(
            f"\n{len(result['under_searched'])} claim(s) are UNDER_SEARCHED. Nothing was found "
            "against them, but the search does not yet support saying so. Run another pass "
            "with different phrasing, covering the missing angles."
        )
        raise SystemExit(2)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
