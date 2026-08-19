# Deploying the Theorem Codex as a website

The web UI is the Streamlit dashboard at
`components/theorem_codex/apps/streamlit_app.py`, backed by a SQLite database
that the app creates and initializes automatically on first run. The dashboard
is read-only — proven results, their proofs, and peer-review scores; proof
work is recorded by the CLI and agents — so a real deployment needs a
persistent disk holding the DB file those tools write. The Docker setup below
handles that with a volume.

## Run locally with Docker

```sh
docker compose up --build
```

Open http://localhost:8501. The database lives in the `codex-data` named
volume as `/data/proof_codex.sqlite`, so it survives rebuilds and restarts.

Without compose:

```sh
docker build -t theorem-codex .
docker run -p 8501:8501 -v codex-data:/data theorem-codex
```

## Deploy to a cloud host

The image respects three environment variables:

- `PORT` — HTTP port to bind (defaults to 8501). Render, Railway, and
  Heroku-style platforms set this automatically.
- `THESIUS_DB` — path to the SQLite file (defaults to
  `/data/proof_codex.sqlite`). Point it at the platform's mounted disk.
- `THESIUS_PASSWORD` — when set, the app shows a sign-in screen and requires
  this password. **Always set this on any deployment reachable from the
  internet.** When unset, the app is open (local-first default).

### Fly.io

```sh
fly launch --no-deploy          # detects the Dockerfile
fly volumes create codex_data --size 1
```

Add to the generated `fly.toml`:

```toml
[mounts]
  source = "codex_data"
  destination = "/data"
```

Then `fly deploy`.

### Render / Railway

Create a new **Web Service** from this repo; both platforms auto-detect the
Dockerfile. Attach a persistent disk (Render: "Disks", Railway: "Volumes")
mounted at `/data`. No other configuration is required.

### Any VPS (DigitalOcean, EC2, etc.)

```sh
git clone <your-repo-url> && cd thesisus
docker compose up -d
```

Put nginx/Caddy in front for TLS, proxying to `localhost:8501`. Streamlit
uses WebSockets, so enable `Upgrade`/`Connection` header forwarding (Caddy
does this automatically).

### Streamlit Community Cloud (free, but ephemeral data)

1. Push this repo to GitHub.
2. On https://share.streamlit.io create an app pointing at
   `components/theorem_codex/apps/streamlit_app.py` on your branch.
3. The root `requirements.txt` is picked up automatically.

**Caveat:** Community Cloud has no persistent disk — the SQLite database is
recreated whenever the app restarts. Fine for demoing the UI; use the Docker
path above for real research data.

## Access control

The app supports two authentication modes, checked in this order:

1. **OIDC single sign-on** (recommended) — used when an `[auth]` section is
   present in Streamlit secrets. Per-user login via Google or any OIDC
   provider, using Streamlit's native `st.login()`.
2. **Shared password** — used when no `[auth]` section exists but
   `THESIUS_PASSWORD` (env var) or `thesius_password` (secrets) is set.

When neither is configured the app is open, which is only appropriate on
your own machine or a trusted network. A "Sign out" button appears under
the Activity panel's Settings expander in both modes.

### OIDC single sign-on setup

1. Register an OAuth client with your provider. For Google: create an
   **OAuth 2.0 Client ID** (type: web application) at
   https://console.cloud.google.com/apis/credentials and add
   `<your-app-origin>/oauth2callback` as an authorized redirect URI
   (e.g. `https://codex.example.com/oauth2callback`, or
   `http://localhost:8501/oauth2callback` for local testing).
2. Copy `.streamlit/secrets.example.toml` to `.streamlit/secrets.toml` and
   fill in `client_id`, `client_secret`, `redirect_uri`, and a random
   `cookie_secret` (`python -c "import secrets; print(secrets.token_hex(32))"`).
3. **Restrict who may sign in.** With a public provider like Google, any
   account can complete login unless you limit it. Set
   `thesius_allowed_emails` in secrets (or the `THESIUS_ALLOWED_EMAILS`
   env var, comma-separated). Non-listed accounts get an "not authorized"
   screen with a sign-out button.

Where the secrets live per platform:

- **Docker / VPS**: uncomment the secrets mount in `docker-compose.yml`
  (mounts `.streamlit/secrets.toml` read-only into the container). The
  file is gitignored and dockerignored so it never ends up in the repo or
  image.
- **Streamlit Community Cloud**: paste the secrets in app
  **Settings → Secrets**.
- **Fly.io / Render / Railway**: use the platform's secret-file mount if
  available, or bake the file onto the persistent disk and point Streamlit
  at it; alternatively run with the password mode below.

OIDC needs `Authlib>=1.3.2`, already included in `requirements.txt`.

### Shared password setup

Set a password via either:

- the `THESIUS_PASSWORD` environment variable (Docker, Fly.io, Render,
  Railway, VPS), e.g. `THESIUS_PASSWORD=change-me docker compose up -d`, or
- a `thesius_password` entry in Streamlit secrets.

This is a single shared password, not per-user accounts — prefer OIDC for
anything multi-user.

### Notes for both modes

- The Settings panel lets a signed-in user run arbitrary SQL against the
  database, so only admit people you'd trust with the data.
- Deploy behind HTTPS (platform-provided TLS, or nginx/Caddy on a VPS).
  OIDC providers generally require an HTTPS redirect URI for non-localhost
  origins, and the auth cookie/password shouldn't travel in cleartext.
