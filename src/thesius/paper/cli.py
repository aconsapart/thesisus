"""Typer commands for the paper pipeline: thesius paper export | write | review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ..db import add_artifact, connect
from ..settings import feature_enabled, get_database_path

paper_app = typer.Typer(help="Generate and review papers from the codex")
console = Console(width=220)


@paper_app.callback()
def paper_main():
    """Gate all paper commands behind the 'paper' feature flag."""
    if not feature_enabled("paper"):
        console.print(
            "[yellow]The paper pipeline is disabled.[/yellow] Enable it with:\n"
            "  thesius config set features.paper true\n"
            "or set THESIUS_FEATURE_PAPER=1 in the environment."
        )
        raise typer.Exit(1)

DB_HELP = "SQLite database path. Overrides configured database.path."


@paper_app.command("export")
def paper_export_cmd(
    theorem: str = typer.Option(..., help="Theorem slug to export."),
    out_dir: str = typer.Option("papers", help="Output directory root."),
    db: Optional[str] = typer.Option(None, "--db", help=DB_HELP),
):
    """Export codex records for a theorem into notes.txt + results.json."""
    from .export import codex_to_notes

    db_path = get_database_path(db)
    target = Path(out_dir) / theorem
    con = connect(db_path)
    try:
        export = codex_to_notes(con, theorem, target)
    finally:
        con.close()
    console.print(f"[green]Exported[/green] {export['notes_path']}")
    console.print(f"[green]Summary[/green] {export['results_path']}")
    if export["figures"]:
        console.print(f"Figures: {', '.join(export['figures'])}")


@paper_app.command("write")
def paper_write_cmd(
    theorem: str = typer.Option(..., help="Theorem slug to write up."),
    out_dir: str = typer.Option("papers", help="Output directory root."),
    model: Optional[str] = typer.Option(None, help="Model id. Defaults to paper.model config, THESIUS_PAPER_MODEL, then claude-opus-5."),
    citations: int = typer.Option(0, help="Semantic Scholar citation rounds (0 = skip; network access required)."),
    compile_pdf: bool = typer.Option(True, "--compile/--no-compile", help="Compile the LaTeX to PDF (requires pdflatex)."),
    use_aider: bool = typer.Option(False, "--use-aider", help="Drive the writeup with aider instead of direct LLM calls."),
    db: Optional[str] = typer.Option(None, "--db", help=DB_HELP),
):
    """Export a theorem, draft a LaTeX paper with an LLM, and compile it."""
    from .writeup import write_paper

    db_path = get_database_path(db)
    target = Path(out_dir) / theorem
    try:
        result = write_paper(
            db_path,
            theorem,
            target,
            model=model,
            citation_rounds=citations,
            compile_pdf=compile_pdf,
            use_aider=use_aider,
        )
    except (RuntimeError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Wrote[/green] {result['tex_path']} (model {result['model']})")
    if result["pdf_path"]:
        console.print(f"[green]Compiled[/green] {result['pdf_path']}")
    elif compile_pdf:
        console.print("[red]LaTeX compilation did not produce a PDF; see latex/ logs.[/red]")


@paper_app.command("review")
def paper_review_cmd(
    paper: str = typer.Argument(..., help="Path to the paper (.pdf, .txt, .md, or .tex)."),
    theorem: Optional[str] = typer.Option(None, help="Theorem slug to link the review to in the codex."),
    model: Optional[str] = typer.Option(None, help="Model id. Defaults to paper.model config, THESIUS_PAPER_MODEL, then claude-opus-5."),
    ensemble: int = typer.Option(1, help="Number of ensembled reviews (meta-reviewed when > 1)."),
    reflections: int = typer.Option(1, help="Reflection rounds on the review."),
    fewshot: int = typer.Option(1, min=0, max=3, help="Number of few-shot example reviews in the prompt."),
    db: Optional[str] = typer.Option(None, "--db", help=DB_HELP),
):
    """Run an LLM peer review of a paper and store it in the codex."""
    from .llm import create_client, resolve_model
    from .review import load_paper, perform_review

    paper_path = Path(paper)
    if not paper_path.is_file():
        console.print(f"[red]Paper not found:[/red] {paper_path}")
        raise typer.Exit(1)

    # Validate the slug before spending any LLM calls, so a typo doesn't
    # silently record an unlinked review artifact.
    db_path = get_database_path(db)
    if theorem is not None:
        from ..db import theorem_id

        con = connect(db_path)
        try:
            if theorem_id(con, theorem) is None:
                console.print(f"[red]No theorem found:[/red] {theorem}")
                raise typer.Exit(1)
        finally:
            con.close()

    try:
        model_id = resolve_model(model)
        client, model_id = create_client(model_id)
        text = load_paper(paper_path)
        review = perform_review(
            text,
            model_id,
            client,
            num_reflections=reflections,
            num_fs_examples=fewshot,
            num_reviews_ensemble=ensemble,
        )
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    review_path = paper_path.with_suffix(".review.json")
    review_path.write_text(json.dumps({"review": review}, indent=2) + "\n", encoding="utf-8")
    console.print_json(json.dumps(review, indent=2))
    console.print(f"[green]Saved review[/green] {review_path}")

    con = connect(db_path)
    try:
        aid = add_artifact(
            con,
            path=str(review_path),
            kind="paper_review",
            theorem_slug=theorem,
            description_md=(
                f"LLM review of {paper_path.name} (model {model_id}): "
                f"Overall {review.get('Overall')}, Decision {review.get('Decision')}."
            ),
        )
    finally:
        con.close()
    console.print(f"[green]Recorded review artifact[/green] id={aid}")
