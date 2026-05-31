# Database setting

Thesius stores the default SQLite database path in:

```text
config/local_cli_settings.json
```

Set it once:

```bash
thesius config set-db proof_codex.sqlite
```

Show the active database:

```bash
thesius config get-db
```

Show all settings:

```bash
thesius config show
```

Override the configured database for one command:

```bash
thesius status --db /tmp/other.sqlite
```

Resolution order:

1. explicit `--db` option;
2. `config/local_cli_settings.json` key `database.path`;
3. legacy keys `database_path`, `db_path`, `database`, `db`;
4. `THESIUS_DB` environment variable;
5. `proof_codex.sqlite`.
