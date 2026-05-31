# Security notes

- Do not commit `config/local_settings.yaml` if it contains API keys.
- Prefer environment variables or a secret manager for shared machines.
- The included `.gitignore` files in components are designed to ignore local settings and run artifacts.
- Datasette should be run read-only unless you intentionally expose write endpoints through plugins.
