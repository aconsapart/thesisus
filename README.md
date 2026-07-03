<div id="top"></div>

<!-- PROJECT SHIELDS -->
[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![MIT License][license-shield]][license-url]

<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://github.com/aconsapart/thesys">
    <img src="images/logo.png" alt="Thesius logo" width="80" height="80">
  </a>

  <h3 align="center">Thesius Suite</h3>

  <p align="center">
    A local-first theorem and proof research workbench.
    <br />
    <a href="docs/INTEGRATION_GUIDE.md"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="#usage">View Usage</a>
    ·
    <a href="https://github.com/aconsapart/thesys/issues">Report Bug</a>
    ·
    <a href="https://github.com/aconsapart/thesys/issues">Request Feature</a>
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#configuration">Configuration</a></li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#deployment">Deployment</a></li>
    <li><a href="#testing">Testing</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

<!-- ABOUT THE PROJECT -->
## About The Project

[![Thesius Suite Screen Shot][product-screenshot]](#usage)

Thesius Suite is a local-first research workbench for theorem and proof exploration. It combines a Python command-line interface, an interactive terminal UI, a SQLite theorem codex, browser-friendly UIs, and research-agent components into one repository.

The project is organized around a few practical goals:

* keep theorem data available locally in SQLite;
* expose the codex through CLI, TUI, Datasette, and Streamlit workflows;
* support LangGraph and LangChain research-agent experiments;
* keep CAS and formalization hooks close to the theorem corpus;
* avoid shell-script-only workflows by providing Python entry points.

Core project documentation lives in `docs/`, while reusable research components live in `components/`.

<p align="right">(<a href="#top">back to top</a>)</p>

### Built With

* [Python](https://www.python.org/)
* [Typer](https://typer.tiangolo.com/)
* [Rich](https://rich.readthedocs.io/)
* [SQLite](https://www.sqlite.org/)
* [Datasette](https://datasette.io/)
* [Streamlit](https://streamlit.io/)
* [LangGraph](https://www.langchain.com/langgraph)
* [LangChain](https://www.langchain.com/)
* [pytest](https://docs.pytest.org/)

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- GETTING STARTED -->
## Getting Started

Follow these steps to install Thesius locally and initialize the theorem codex.

### Prerequisites

* Python 3.10 or newer
* Git
* Optional: API credentials for any agent workflows that call external model providers

### Installation

1. Clone the repo.
   ```sh
   git clone git@github.com:aconsapart/thesys.git
   cd thesys
   ```
2. Create and activate a virtual environment.
   ```sh
   python -m venv .venv
   source .venv/bin/activate
   ```
3. Install the package with test and agent dependencies.
   ```sh
   pip install -U pip
   pip install -e ".[test,agents]"
   ```
4. Initialize the theorem codex.
   ```sh
   thesius init
   ```

You can also initialize the codex with Python only:

```sh
python -m scripts.init_codex
```

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- CONFIGURATION -->
## Configuration

Thesius stores the default SQLite database path in `config/local_cli_settings.json`. That local settings file is ignored by git.

Set a default database once:

```sh
thesius config set-db proof_codex.sqlite
```

Inspect the configured database:

```sh
thesius config get-db
thesius config show
```

Every command uses the configured database by default. Override it for a single command with `--db`:

```sh
thesius status --db another_codex.sqlite
```

Initialize and save a database path in one step:

```sh
thesius init --db proof_codex.sqlite --save-db
```

See `config/local_cli_settings.example.json` for a local settings template.

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- USAGE EXAMPLES -->
## Usage

Start the command-line TUI:

```sh
thesius tui
```

Common TUI commands:

```text
status
frontier
strategies
show <theorem_slug>
add-attempt <theorem_slug> <strategy_slug> <STATUS> <text...>
add-falsification <theorem_slug> <strategy_slug> <SEVERITY> <text...>
quit
```

Run direct CLI commands:

```sh
thesius status
thesius frontier
thesius strategies
thesius theorem exact-short-box-product-fiber-curve-intersection
```

Launch browser UIs without shell scripts:

```sh
thesius serve streamlit
thesius serve datasette
```

Run the generic workbench agent:

```sh
thesius run workbench \
  --iterations 3 \
  --parallel-strategies 3 \
  --out runs/workbench_example
```

More details:

* `docs/PYTHON_TUI.md`
* `docs/DATABASE_SETTING.md`
* `docs/INTEGRATION_GUIDE.md`
* `docs/COMPONENTS.md`
* `docs/TESTING.md`

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- DEPLOYMENT -->
## Deployment

Deploy the Theorem Codex dashboard as a website with Docker:

```sh
THESIUS_PASSWORD=change-me docker compose up --build
```

The app serves on port 8501 with the SQLite database on a persistent volume,
and requires the password whenever `THESIUS_PASSWORD` is set. Google/OIDC
single sign-on is also supported via Streamlit secrets (see
`.streamlit/secrets.example.toml`).

Follow the step-by-step runbook in [`DEPLOY.md`](DEPLOY.md) to go live on
Fly.io, Render/Railway, a VPS, or Streamlit Community Cloud; reference
details are in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- TESTING -->
## Testing

Run the test suite from the project root:

```sh
pytest -q
```

If the package is not installed in the active environment, run tests against the source tree:

```sh
PYTHONPATH=src pytest -q
```

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- ROADMAP -->
## Roadmap

- [x] Package the Thesius CLI as a Python entry point
- [x] Add a Python TUI for codex workflows
- [x] Add local database configuration
- [x] Add Datasette and Streamlit launch commands
- [x] Include research-agent components
- [ ] Expand automated coverage for agent and UI workflows
- [ ] Add more formalization and CAS integration examples

See the [open issues](https://github.com/aconsapart/thesys/issues) for proposed features and known issues.

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- CONTRIBUTING -->
## Contributing

Contributions should keep the project local-first, Python-driven, and easy to test.

1. Fork the project.
2. Create your feature branch (`git checkout -b feature/amazing-feature`).
3. Commit your changes (`git commit -m 'Add amazing feature'`).
4. Push to the branch (`git push origin feature/amazing-feature`).
5. Open a pull request.

Before opening a pull request, run:

```sh
pytest -q
```

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- LICENSE -->
## License

Distributed under the MIT License. See `LICENSE.txt` for more information.

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- CONTACT -->
## Contact

Project Link: [https://github.com/aconsapart/thesys](https://github.com/aconsapart/thesys)

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- ACKNOWLEDGMENTS -->
## Acknowledgments

This project builds on the Python scientific and developer tooling ecosystem, including Typer, Rich, SQLite, Datasette, Streamlit, LangGraph, LangChain, and pytest.

The README layout follows the structure of [Best-README-Template](https://github.com/othneildrew/Best-README-Template).

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->
[contributors-shield]: https://img.shields.io/github/contributors/aconsapart/thesys.svg?style=for-the-badge
[contributors-url]: https://github.com/aconsapart/thesys/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/aconsapart/thesys.svg?style=for-the-badge
[forks-url]: https://github.com/aconsapart/thesys/network/members
[stars-shield]: https://img.shields.io/github/stars/aconsapart/thesys.svg?style=for-the-badge
[stars-url]: https://github.com/aconsapart/thesys/stargazers
[issues-shield]: https://img.shields.io/github/issues/aconsapart/thesys.svg?style=for-the-badge
[issues-url]: https://github.com/aconsapart/thesys/issues
[license-shield]: https://img.shields.io/github/license/aconsapart/thesys.svg?style=for-the-badge
[license-url]: https://github.com/aconsapart/thesys/blob/master/LICENSE.txt
[product-screenshot]: images/screenshot.png
