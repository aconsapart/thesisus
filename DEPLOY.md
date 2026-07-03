# How to deploy Thesius as a website

This is the step-by-step runbook. Reference material (all platforms, env
vars, auth details) lives in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

What gets deployed: the Theorem Codex dashboard
(`components/theorem_codex/apps/streamlit_app.py`), a Streamlit app backed
by a SQLite database it creates on first run. The database is written to a
persistent volume so your research data survives restarts.

---

## Step 1 — Decide on authentication

Pick one before exposing anything to the internet:

| Mode | Good for | Setup |
|------|----------|-------|
| Google/OIDC SSO | Real deployments, multiple users | Step 2 below |
| Shared password | Quick single-user deploys | `export THESIUS_PASSWORD=change-me` |
| None | localhost only | nothing |

## Step 2 — (SSO only) Create the OAuth client and secrets file

Skip this step if you're using the shared password.

1. Go to https://console.cloud.google.com/apis/credentials → **Create
   Credentials → OAuth client ID → Web application**.
2. Add an authorized redirect URI: `https://<your-domain>/oauth2callback`
   (use `http://localhost:8501/oauth2callback` while testing locally).
3. Create your secrets file and fill in the client ID/secret it gives you:

   ```sh
   cp .streamlit/secrets.example.toml .streamlit/secrets.toml
   python3 -c "import secrets; print(secrets.token_hex(32))"   # -> cookie_secret
   ```

4. In `secrets.toml`, set `thesius_allowed_emails` to the accounts allowed
   in — otherwise **any Google account can sign in**.
5. Uncomment the secrets mount in `docker-compose.yml`:

   ```yaml
   - ./.streamlit/secrets.toml:/app/.streamlit/secrets.toml:ro
   ```

`secrets.toml` is gitignored and dockerignored — never commit it.

## Step 3 — Run it locally and check it works

```sh
docker compose up --build            # add THESIUS_PASSWORD=... in front for password mode
```

Open http://localhost:8501. Confirm you hit the sign-in screen (if you
configured auth), sign in, and create a test project. Data persists in the
`codex-data` Docker volume.

## Step 4 — Deploy to the internet

### Option A: Fly.io (recommended — free-tier friendly, persistent disk, TLS included)

```sh
brew install flyctl && fly auth signup     # first time only
fly launch --no-deploy                     # detects the Dockerfile; pick a region
fly volumes create codex_data --size 1
```

Add to the generated `fly.toml`:

```toml
[mounts]
  source = "codex_data"
  destination = "/data"
```

Set your auth secrets, then deploy:

```sh
# password mode:
fly secrets set THESIUS_PASSWORD=change-me

# or SSO mode — ship the secrets file alongside the machine:
fly secrets set THESIUS_ALLOWED_EMAILS=you@example.com
# and copy .streamlit/secrets.toml contents into fly.toml [[files]] or a
# secret-mounted file; see https://fly.io/docs/reference/configuration/#the-files-section

fly deploy
fly open
```

Your app is live at `https://<app-name>.fly.dev`. For SSO, go back to the
Google console and set the redirect URI to
`https://<app-name>.fly.dev/oauth2callback`.

### Option B: Render / Railway

1. Push the repo to GitHub (already done: `aconsapart/thesisus`).
2. Create a **Web Service** from the repo — the Dockerfile is auto-detected.
3. Attach a persistent disk (Render: *Disks*; Railway: *Volumes*) mounted at
   `/data`.
4. Set `THESIUS_PASSWORD` in the service's environment settings (or provide
   Streamlit secrets via the platform's secret-file feature for SSO).

### Option C: Your own VPS

```sh
git clone git@github.com:aconsapart/thesisus.git && cd thesisus
# set up auth per Steps 1–2
docker compose up -d
```

Put Caddy in front for automatic HTTPS (`Caddyfile`):

```
codex.example.com {
    reverse_proxy localhost:8501
}
```

Caddy handles the WebSocket upgrade Streamlit needs automatically.

### Option D: Streamlit Community Cloud (free demo, no persistent data)

1. On https://share.streamlit.io, create an app from the repo, main file
   `components/theorem_codex/apps/streamlit_app.py`.
2. Paste your auth config into **Settings → Secrets** (contents of
   `secrets.toml`, or just `thesius_password = "change-me"`).

**Warning:** no persistent disk — the database resets on every restart.
Demo only.

## Step 5 — Verify the deployment

- [ ] Visiting the URL in a private browser window shows the sign-in
      screen, not the dashboard.
- [ ] A non-allowlisted account (SSO) or wrong password is rejected.
- [ ] Create a project, restart the app (`fly apps restart` /
      `docker compose restart`), confirm the project is still there.
- [ ] URL is `https://` (all options above except a bare VPS give you TLS
      automatically).
