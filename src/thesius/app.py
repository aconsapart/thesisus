from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from . import __version__
from .db import (
    add_attempt,
    add_falsification,
    connect,
    init_db,
    rows,
    seed,
    table_count,
    upsert_theorem,
)

app = typer.Typer(help="Thesius CLI/TUI", no_args_is_help=True, invoke_without_command=True)
serve_app = typer.Typer(help="Launch optional UIs")
run_app = typer.Typer(help="Run agents and external tools")
add_app = typer.Typer(help="Add records to the codex")
config_app = typer.Typer(help="Manage local JSON settings")
app.add_typer(serve_app, name="serve")
app.add_typer(run_app, name="run")
app.add_typer(add_app, name="add")
app.add_typer(config_app, name="config")

console = Console(width=220)
DEFAULT_DB = "proof_codex.sqlite"
CONFIG_PATH = Path(os.environ.get("THESIUS_CONFIG", "config/local_cli_settings.json"))


def _load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_config(data: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _get_nested(data: dict[str, Any], key: str, default: Any = None) -> Any:
    cur: Any = data
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _set_nested(data: dict[str, Any], key: str, value: Any) -> None:
    cur = data
    parts = key.split(".")
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _db_path(db: Optional[str]) -> str:
    """Resolve the codex SQLite database path.

    Resolution order:
        1. explicit --db argument,
        2. config/local_cli_settings.json: database.path,
        3. legacy config keys: database_path, db_path, database, db,
        4. THESIUS_DB environment variable,
        5. proof_codex.sqlite.
    """
    if db:
        return db
    cfg = _load_config()
    configured = (
        _get_nested(cfg, "database.path")
        or cfg.get("database_path")
        or cfg.get("db_path")
        or cfg.get("database")
        or cfg.get("db")
    )
    if configured:
        return str(configured)
    return os.environ.get("THESIUS_DB", DEFAULT_DB)


def _db_option_help() -> str:
    return "SQLite database path override. If omitted, uses config/local_cli_settings.json database.path, THESIUS_DB, then proof_codex.sqlite."


def _print_rows_table(title: str, data, columns: list[str]) -> None:
    table = Table(title=title)
    for col in columns:
        table.add_column(col, overflow="fold", no_wrap=False)
    for row in data:
        table.add_row(*[str(row[col]) if row[col] is not None else "" for col in columns])
    console.print(table)


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
):
    if version:
        console.print(f"thesius {__version__}")
        raise typer.Exit()


@app.command("init")
def init_cmd(
    db: Optional[str] = typer.Option(None, "--db", help="SQLite database path. Overrides configured database.path."),
    with_seed: bool = typer.Option(True, "--seed/--no-seed", help="Seed the current theorem frontier."),
    save_db: bool = typer.Option(False, "--save-db/--no-save-db", help="Persist the resolved SQLite path to config/local_cli_settings.json."),
):
    """Initialize the theorem codex database."""
    db_path = _db_path(db)
    if save_db:
        data = _load_config()
        _set_nested(data, "database.path", db_path)
        _save_config(data)
    if with_seed:
        seed(db_path)
    else:
        init_db(db_path)
    console.print(f"[green]Initialized[/green] {db_path}")
    if save_db:
        console.print(f"[green]Saved default database[/green] {db_path}")


@app.command("status")
def status_cmd(db: Optional[str] = typer.Option(None, "--db", help="SQLite database path. Overrides configured database.path.")):
    """Show codex status summary."""
    db_path = _db_path(db)
    typer.echo(f"Database: {db_path}")
    con = connect(db_path)
    try:
        counts = {name: table_count(con, name) for name in ["theorem", "strategy", "attempt", "falsification", "computation", "artifact"]}
        console.print(f"Database path: {db_path}")
        table = Table(title="Codex status")
        table.add_column("Table")
        table.add_column("Rows", justify="right")
        for key, val in counts.items():
            table.add_row(key, str(val))
        console.print(table)
        frontier = rows(con, "SELECT slug,title,status,frontier_rank FROM v_current_frontier LIMIT 10")
        if frontier:
            _print_rows_table("Current frontier", frontier, ["frontier_rank", "slug", "status", "title"])
    finally:
        con.close()


@app.command("frontier")
def frontier_cmd(db: Optional[str] = typer.Option(None, "--db", help="SQLite database path. Overrides configured database.path.")):
    """List current frontier theorems."""
    db_path = _db_path(db)
    con = connect(db_path)
    try:
        data = rows(con, "SELECT frontier_rank, slug, status, title FROM v_current_frontier")
        _print_rows_table("Current Frontier", data, ["frontier_rank", "slug", "status", "title"])
    finally:
        con.close()


@app.command("strategies")
def strategies_cmd(db: Optional[str] = typer.Option(None, "--db", help="SQLite database path. Overrides configured database.path.")):
    """List strategies and health metrics."""
    db_path = _db_path(db)
    con = connect(db_path)
    try:
        data = rows(con, "SELECT slug,name,status,rank,score,attempts,proved_attempts,open_attempts FROM v_strategy_health ORDER BY rank, score DESC")
        _print_rows_table("Strategies", data, ["rank", "slug", "status", "score", "attempts", "proved_attempts", "open_attempts"])
    finally:
        con.close()


@app.command("theorem")
def theorem_show_cmd(slug: str, db: Optional[str] = typer.Option(None, "--db", help="SQLite database path. Overrides configured database.path.")):
    """Show a theorem by slug."""
    db_path = _db_path(db)
    con = connect(db_path)
    try:
        data = rows(con, "SELECT * FROM theorem WHERE slug=?", (slug,))
        if not data:
            console.print(f"[red]No theorem found:[/red] {slug}")
            raise typer.Exit(1)
        row = data[0]
        console.print(Panel(f"[bold]{row['title']}[/bold]\n{row['status']} • {row['kind']} • rank {row['frontier_rank']}", title=row["slug"]))
        console.print(Markdown(row["statement_md"]))
        claims = rows(con, "SELECT status, claim_md FROM claim WHERE theorem_id=? ORDER BY created_at DESC", (row["id"],))
        if claims:
            _print_rows_table("Claims", claims, ["status", "claim_md"])
    finally:
        con.close()


@add_app.command("theorem")
def add_theorem_cmd(
    slug: str = typer.Option(...),
    title: str = typer.Option(...),
    statement: str = typer.Option(..., help="Markdown statement or @path/to/file.md"),
    status: str = typer.Option("FAILED/OPEN"),
    kind: str = typer.Option("THEOREM"),
    frontier_rank: Optional[int] = typer.Option(None),
    frontier: bool = typer.Option(False, "--frontier/--not-frontier"),
    db: Optional[str] = typer.Option(None, "--db", help="SQLite database path. Overrides configured database.path."),
):
    """Add or update a theorem."""
    db_path = _db_path(db)
    statement_md = Path(statement[1:]).read_text(encoding="utf-8") if statement.startswith("@") else statement
    con = connect(db_path)
    try:
        tid = upsert_theorem(con, slug=slug, title=title, statement_md=statement_md, status=status, kind=kind, frontier_rank=frontier_rank, is_frontier=frontier)
        console.print(f"[green]Saved theorem[/green] {slug} (id={tid})")
    finally:
        con.close()


@add_app.command("attempt")
def add_attempt_cmd(
    theorem: Optional[str] = typer.Option(None),
    strategy: Optional[str] = typer.Option(None),
    title: Optional[str] = typer.Option(None),
    prompt: str = typer.Option("", help="Prompt text or @path"),
    result: str = typer.Option(..., help="Result text or @path"),
    status: str = typer.Option("FAILED/OPEN"),
    run_id: str = typer.Option("manual"),
    model: Optional[str] = typer.Option(None),
    db: Optional[str] = typer.Option(None, "--db", help="SQLite database path. Overrides configured database.path."),
):
    """Add a proof attempt record."""
    db_path = _db_path(db)
    prompt_md = Path(prompt[1:]).read_text(encoding="utf-8") if prompt.startswith("@") else prompt
    result_md = Path(result[1:]).read_text(encoding="utf-8") if result.startswith("@") else result
    con = connect(db_path)
    try:
        aid = add_attempt(con, theorem_slug=theorem, strategy_slug=strategy, run_id=run_id, title=title, prompt_md=prompt_md, result_md=result_md, status=status, model=model)
        console.print(f"[green]Added attempt[/green] id={aid}")
    finally:
        con.close()


@add_app.command("falsification")
def add_falsification_cmd(
    theorem: Optional[str] = typer.Option(None),
    strategy: Optional[str] = typer.Option(None),
    obstruction: str = typer.Option(..., help="Obstruction text or @path"),
    counterexample: Optional[str] = typer.Option(None, help="Counterexample text or @path"),
    severity: str = typer.Option("MEDIUM"),
    db: Optional[str] = typer.Option(None, "--db", help="SQLite database path. Overrides configured database.path."),
):
    """Add a falsification/obstruction record."""
    db_path = _db_path(db)
    obstruction_md = Path(obstruction[1:]).read_text(encoding="utf-8") if obstruction.startswith("@") else obstruction
    counterexample_md = None if counterexample is None else (Path(counterexample[1:]).read_text(encoding="utf-8") if counterexample.startswith("@") else counterexample)
    con = connect(db_path)
    try:
        fid = add_falsification(con, theorem_slug=theorem, strategy_slug=strategy, obstruction_md=obstruction_md, counterexample_md=counterexample_md, severity=severity)
        console.print(f"[green]Added falsification[/green] id={fid}")
    finally:
        con.close()


@config_app.command("set")
def config_set_cmd(key: str, value: str):
    """Set a local CLI config key in config/local_cli_settings.json. Supports dotted keys."""
    data = _load_config()
    _set_nested(data, key, value)
    _save_config(data)
    console.print(f"[green]Set[/green] {key}")


@config_app.command("set-db")
def config_set_db_cmd(path: str):
    """Set the default SQLite database path used when --db is omitted."""
    data = _load_config()
    _set_nested(data, "database.path", path)
    _save_config(data)
    console.print(f"[green]Default database set[/green] {path} (Set default database)")


@config_app.command("get-db")
def config_get_db_cmd():
    """Print the effective default SQLite database path."""
    typer.echo(_db_path(None))


@config_app.command("show")
def config_show_cmd():
    """Show local CLI config and effective database path."""
    data = _load_config()
    rendered = dict(data)
    rendered["effective_database_path"] = _db_path(None)
    if not CONFIG_PATH.exists():
        console.print("No config/local_cli_settings.json yet. Showing effective defaults.")
    console.print_json(json.dumps(rendered, indent=2, sort_keys=True))


@serve_app.command("streamlit")
def serve_streamlit_cmd(db: Optional[str] = typer.Option(None, "--db", help="SQLite database path. Overrides configured database.path.")):
    """Launch the Streamlit codex dashboard."""
    db_path = _db_path(db)
    app_path = Path("components/theorem_codex/apps/streamlit_app.py")
    if not app_path.exists():
        console.print("[red]Streamlit app not found.[/red]")
        raise typer.Exit(1)
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path), "--", "--db", db_path], check=False)


@serve_app.command("datasette")
def serve_datasette_cmd(db: Optional[str] = typer.Option(None, "--db", help="SQLite database path. Overrides configured database.path.")):
    """Launch Datasette for read-only codex browsing."""
    db_path = _db_path(db)
    metadata = Path("components/theorem_codex/datasette/metadata.json")
    cmd = [sys.executable, "-m", "datasette", "serve", db_path]
    if metadata.exists():
        cmd += ["--metadata", str(metadata)]
    subprocess.run(cmd, check=False)


@run_app.command("workbench")
def run_workbench_cmd(
    problem: str = typer.Option("components/math_research_workbench/examples/generic_number_theory_problem.yaml"),
    strategies: str = typer.Option("components/math_research_workbench/examples/generic_strategy_portfolio.yaml"),
    iterations: int = typer.Option(3),
    parallel_strategies: int = typer.Option(3),
    parallel_refutations: int = typer.Option(1, help="Refutation lanes reserved per iteration."),
    out: str = typer.Option("runs/workbench_example"),
    db: Optional[str] = typer.Option(None, "--db", help="SQLite database path. Overrides configured database.path."),
):
    """Run the generic math workbench agent without shell scripts."""
    db_path = _db_path(db)
    script = Path("components/math_research_workbench/scripts/run_agent.py")
    if not script.exists():
        console.print("[red]Workbench run_agent.py not found.[/red]")
        raise typer.Exit(1)
    cmd = [
        sys.executable, str(script),
        "--problem", problem,
        "--strategies", strategies,
        "--iterations", str(iterations),
        "--parallel-strategies", str(parallel_strategies),
        "--parallel-refutations", str(parallel_refutations),
        "--out", out,
        "--db", db_path,
    ]
    console.print("[bold]Running:[/bold] " + " ".join(shlex.quote(c) for c in cmd))
    subprocess.run(cmd, check=False)


@run_app.command("recon")
def run_recon_cmd(
    problem: str = typer.Option("components/math_research_workbench/examples/counterexample_demo_problem.yaml"),
    emit_prompts: bool = typer.Option(False, "--emit-prompts", help="Print the hostile-search prompts and exit."),
    ingest: Optional[list[str]] = typer.Option(None, "--ingest", help="Search-pass response files to grade."),
    prompt_dir: Optional[str] = typer.Option(None, help="Also write emitted prompts here."),
    out: Optional[str] = typer.Option(None, help="Write the threat-table report here."),
    claims_out: Optional[str] = typer.Option(None, help="Write the defensible claim set here."),
    db: Optional[str] = typer.Option(None, "--db", help="Persist the threat table to this codex."),
):
    """Hostile prior-art recon: has someone already published this?

    Day-zero work. The cheapest way for a claim to die is for it to already
    exist, so this runs before any proof or refutation budget is committed.

    Exit code 1 means a claim was killed or wounded (the search did its job).
    Exit code 2 means a claim is under-searched: nothing was found, but not
    thoroughly enough to say so.
    """
    script = Path("components/math_research_workbench/scripts/recon.py")
    if not script.exists():
        console.print("[red]Workbench recon.py not found.[/red]")
        raise typer.Exit(1)
    cmd = [sys.executable, str(script), "--problem", problem]
    if emit_prompts:
        cmd.append("--emit-prompts")
        if prompt_dir:
            cmd += ["--prompt-dir", prompt_dir]
    elif ingest:
        cmd += ["--ingest", *ingest]
        if db is not None:
            cmd += ["--db", _db_path(db)]
        if out:
            cmd += ["--out", out]
        if claims_out:
            cmd += ["--claims-out", claims_out]
    else:
        console.print("[red]Give either --emit-prompts or --ingest.[/red]")
        raise typer.Exit(1)
    console.print("[bold]Running:[/bold] " + " ".join(shlex.quote(c) for c in cmd))
    result = subprocess.run(cmd, check=False)
    raise typer.Exit(result.returncode)


@run_app.command("sweep")
def run_sweep_cmd(
    problem: str = typer.Option("components/math_research_workbench/examples/counterexample_demo_problem.yaml"),
    out: Optional[str] = typer.Option(None, help="Write the markdown report here."),
    db: Optional[str] = typer.Option(None, "--db", help="Persist results to this codex. Omit to only print."),
    max_evaluations: Optional[int] = typer.Option(None),
    time_limit: Optional[float] = typer.Option(None),
):
    """Search a problem's conjectures for counterexamples.

    Deterministic and free: no model call, no API key. Worth running before
    committing to a proof campaign. Exit code 1 means a conjecture was
    falsified, which is a successful run of this command. Exit code 2 means the
    two independent evaluators disagreed somewhere and the run is not
    trustworthy until that is fixed.
    """
    script = Path("components/math_research_workbench/scripts/sweep.py")
    if not script.exists():
        console.print("[red]Workbench sweep.py not found.[/red]")
        raise typer.Exit(1)
    cmd = [sys.executable, str(script), "--problem", problem]
    if db is not None:
        cmd += ["--db", _db_path(db)]
    if out:
        cmd += ["--out", out]
    if max_evaluations is not None:
        cmd += ["--max-evaluations", str(max_evaluations)]
    if time_limit is not None:
        cmd += ["--time-limit", str(time_limit)]
    console.print("[bold]Running:[/bold] " + " ".join(shlex.quote(c) for c in cmd))
    result = subprocess.run(cmd, check=False)
    raise typer.Exit(result.returncode)


@app.command("tui")
def tui_cmd(
    db: Optional[str] = typer.Option(None, "--db", help="SQLite database path. Overrides configured database.path."),
    commands: Optional[str] = typer.Option(None, "--commands", help="Semicolon-separated commands for tests or scripted runs."),
):
    """Interactive command-loop TUI, similar in spirit to coding-agent CLIs."""
    db_path = _db_path(db)
    seed(db_path) if not Path(db_path).exists() else init_db(db_path)
    console.print(Panel(f"Thesius TUI\nDB: {db_path}\nType 'help' for commands, 'quit' to exit.", title="thesius"))

    def handle(line: str) -> bool:
        parts = shlex.split(line)
        if not parts:
            return True
        cmd = parts[0].lower()
        if cmd in {"quit", "exit", "q"}:
            return False
        if cmd == "help":
            console.print(Markdown("""
Commands:
- `status` — show counts and frontier
- `frontier` — list current frontier
- `strategies` — list strategies
- `show <slug>` — show theorem
- `add-attempt <theorem_slug> <strategy_slug> <status> <text...>`
- `add-falsification <theorem_slug> <strategy_slug> <severity> <text...>`
- `quit` — exit
"""))
            return True
        if cmd == "status":
            status_cmd(db=db_path)
            return True
        if cmd == "frontier":
            frontier_cmd(db=db_path)
            return True
        if cmd == "strategies":
            strategies_cmd(db=db_path)
            return True
        if cmd == "show" and len(parts) >= 2:
            theorem_show_cmd(parts[1], db=db_path)
            return True
        if cmd == "add-attempt" and len(parts) >= 5:
            theorem, strategy, status = parts[1], parts[2], parts[3]
            text = " ".join(parts[4:])
            con = connect(db_path)
            try:
                aid = add_attempt(con, theorem_slug=theorem, strategy_slug=strategy, run_id="tui", title=None, prompt_md="", result_md=text, status=status)
                console.print(f"[green]Added attempt[/green] id={aid}")
            finally:
                con.close()
            return True
        if cmd == "add-falsification" and len(parts) >= 5:
            theorem, strategy, severity = parts[1], parts[2], parts[3]
            text = " ".join(parts[4:])
            con = connect(db_path)
            try:
                fid = add_falsification(con, theorem_slug=theorem, strategy_slug=strategy, obstruction_md=text, severity=severity)
                console.print(f"[green]Added falsification[/green] id={fid}")
            finally:
                con.close()
            return True
        console.print(f"[red]Unknown command:[/red] {line}")
        return True

    if commands is not None:
        for line in commands.split(";"):
            if not handle(line.strip()):
                break
        return

    while True:
        line = Prompt.ask("[bold cyan]thesius[/bold cyan]")
        if not handle(line):
            break


if __name__ == "__main__":
    app()
