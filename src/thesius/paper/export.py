"""Export codex records for one theorem into the folder layout the writeup expects.

This is the adapter between the Thesius SQLite codex and the AI-Scientist-style
writeup stage: it produces ``notes.txt`` (a structured research log), a
``results.json`` summary, and copies figure artifacts next to them.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from ..db import rows

MAX_FIELD_CHARS = 4000
MAX_REPORT_CHARS = 8000
FIGURE_SUFFIXES = {".png", ".jpg", ".jpeg", ".pdf"}
# Artifacts produced by the paper pipeline itself must never be re-exported
# as figures, or a re-run would embed the previous paper in the new one.
NON_FIGURE_KINDS = {"paper", "paper_tex", "paper_review"}


def _clip(text: str | None, limit: int = MAX_FIELD_CHARS) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... truncated, {len(text) - limit} more characters ...]"


def codex_to_notes(
    con: sqlite3.Connection, theorem_slug: str, out_dir: str | Path
) -> dict[str, Any]:
    """Export everything the codex knows about one theorem.

    Writes ``notes.txt``, ``results.json``, and figure files into ``out_dir``.
    Returns a summary dict with the theorem row, output paths, and figure names.
    Raises ValueError if the slug is unknown.
    """
    theorems = rows(con, "SELECT * FROM theorem WHERE slug=?", (theorem_slug,))
    if not theorems:
        raise ValueError(f"No theorem found with slug: {theorem_slug}")
    theorem = dict(theorems[0])
    tid = theorem["id"]

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    claims = [dict(r) for r in rows(
        con, "SELECT status, claim_md, proof_sketch_md, created_at FROM claim "
        "WHERE theorem_id=? ORDER BY created_at", (tid,))]
    attempts = [dict(r) for r in rows(
        con,
        "SELECT a.created_at, a.run_id, a.title, a.status, a.model, a.result_md, "
        "s.slug AS strategy_slug, s.name AS strategy_name "
        "FROM attempt a LEFT JOIN strategy s ON s.id=a.strategy_id "
        "WHERE a.theorem_id=? ORDER BY a.created_at", (tid,))]
    falsifications = [dict(r) for r in rows(
        con,
        "SELECT f.created_at, f.severity, f.obstruction_md, f.counterexample_md, "
        "s.slug AS strategy_slug "
        "FROM falsification f LEFT JOIN strategy s ON s.id=f.strategy_id "
        "WHERE f.theorem_id=? ORDER BY f.created_at", (tid,))]
    computations = [dict(r) for r in rows(
        con,
        "SELECT created_at, run_id, name, status, code_path, report_path, summary_json "
        "FROM computation WHERE theorem_id=? ORDER BY created_at", (tid,))]
    artifacts = [dict(r) for r in rows(
        con, "SELECT kind, path, description_md FROM artifact WHERE theorem_id=?",
        (tid,))]
    strategies = [dict(r) for r in rows(
        con,
        "SELECT slug, name, status, rank, score, attempts, proved_attempts, "
        "open_attempts FROM v_strategy_health ORDER BY rank, score DESC")]

    figures: list[str] = []
    for art in artifacts:
        if art["kind"] in NON_FIGURE_KINDS:
            continue
        src = Path(art["path"])
        if src.suffix.lower() not in FIGURE_SUFFIXES or not src.is_file():
            continue
        if src.name in figures:
            print(f"Skipping figure with duplicate name: {src}")
            continue
        dest = out / src.name
        if src.resolve() != dest.resolve():
            shutil.copy(src, dest)
        figures.append(src.name)

    lines: list[str] = []
    lines.append(f"# Research notes: {theorem['title']}")
    lines.append("")
    lines.append(f"Slug: {theorem['slug']}")
    lines.append(f"Status: {theorem['status']}  |  Kind: {theorem['kind']}  |  "
                 f"Confidence: {theorem['confidence']}")
    lines.append("")
    lines.append("## Statement")
    lines.append(theorem["statement_md"])

    if claims:
        lines.append("")
        lines.append("## Claims")
        for c in claims:
            lines.append(f"- [{c['status']}] {_clip(c['claim_md'])}")
            if c.get("proof_sketch_md"):
                lines.append(f"  Proof sketch: {_clip(c['proof_sketch_md'])}")

    lines.append("")
    lines.append("## Strategy portfolio (codex-wide health)")
    for s in strategies:
        lines.append(
            f"- {s['slug']} (rank {s['rank']}, status {s['status']}, score "
            f"{s['score']}): {s['attempts'] or 0} attempts, "
            f"{s['proved_attempts'] or 0} proved, {s['open_attempts'] or 0} open"
        )

    if attempts:
        lines.append("")
        lines.append("## Proof attempts")
        for a in attempts:
            header = f"### [{a['status']}] {a['title'] or '(untitled attempt)'}"
            lines.append(header)
            lines.append(
                f"Strategy: {a['strategy_slug'] or 'none'}  |  Run: {a['run_id']}  |  "
                f"Model: {a['model'] or 'n/a'}  |  {a['created_at']}"
            )
            lines.append(_clip(a["result_md"]))
            lines.append("")

    if falsifications:
        lines.append("")
        lines.append("## Falsifications and obstructions")
        for f in falsifications:
            lines.append(f"### [{f['severity']}] via {f['strategy_slug'] or 'unknown strategy'}")
            lines.append(_clip(f["obstruction_md"]))
            if f.get("counterexample_md"):
                lines.append(f"Counterexample: {_clip(f['counterexample_md'])}")
            lines.append("")

    if computations:
        lines.append("")
        lines.append("## Computations (CAS verification)")
        for comp in computations:
            lines.append(f"### [{comp['status']}] {comp['name']} (run {comp['run_id']})")
            summary = comp.get("summary_json")
            if summary:
                try:
                    parsed = json.loads(summary)
                    lines.append("Summary: " + json.dumps(parsed, indent=2)[:MAX_FIELD_CHARS])
                except (json.JSONDecodeError, TypeError):
                    lines.append("Summary: " + _clip(str(summary)))
            report_path = comp.get("report_path")
            if report_path and Path(report_path).is_file():
                lines.append("Report contents:")
                lines.append(_clip(
                    Path(report_path).read_text(encoding="utf-8", errors="replace"),
                    MAX_REPORT_CHARS,
                ))
            lines.append("")

    if figures:
        lines.append("")
        lines.append("## Available figures")
        for name in figures:
            lines.append(f"- {name}")

    notes_path = out / "notes.txt"
    notes_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    results = {
        "theorem": {
            "slug": theorem["slug"],
            "title": theorem["title"],
            "status": theorem["status"],
            "kind": theorem["kind"],
            "confidence": theorem["confidence"],
        },
        "counts": {
            "claims": len(claims),
            "attempts": len(attempts),
            "falsifications": len(falsifications),
            "computations": len(computations),
        },
        "attempts_by_status": _count_by(attempts, "status"),
        "computations_by_status": _count_by(computations, "status"),
        "falsifications_by_severity": _count_by(falsifications, "severity"),
        "figures": figures,
    }
    results_path = out / "results.json"
    results_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    return {
        "theorem": theorem,
        "notes_path": notes_path,
        "results_path": results_path,
        "results": results,
        "figures": figures,
    }


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(key))
        counts[value] = counts.get(value, 0) + 1
    return counts
