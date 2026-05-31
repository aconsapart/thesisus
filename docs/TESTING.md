# Test Suite

Run:

```bash
pytest -q
```

The tests cover:

- database initialization and seeding,
- direct CLI status/frontier commands,
- theorem insertion,
- proof-attempt insertion,
- scripted TUI commands,
- local config commands.

The tests do not require OpenAI, Lean, Aristotle, Sage, Magma, Datasette, or Streamlit servers.
