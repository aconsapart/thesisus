# Python TUI / CLI Design

The suite now uses `thesius`, a Python Typer + Rich CLI/TUI.

Why this shape:

- **Typer** gives composable subcommands and testable CLI behavior.
- **Rich** gives panels, tables, Markdown output, and readable terminal status screens.
- The interactive `thesius tui` loop mimics coding-agent CLI tools by accepting short commands such as `status`, `frontier`, `strategies`, and `show <slug>`.
- The same functionality is exposed as non-interactive commands for tests and automation.

No shell scripts are required.


## Default database setting

Set the default database once:

```bash
thesius config set-db proof_codex.sqlite
thesius config get-db
```

This writes `config/local_cli_settings.json`; `config/local_cli_settings.example.json` is included as a template. Commands use this configured database unless `--db` is passed.


You can also initialize and save the database path in one step:

```bash
thesius init --db proof_codex.sqlite --save-db
```
