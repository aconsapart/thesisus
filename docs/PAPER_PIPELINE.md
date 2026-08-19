# Paper pipeline

Turn the contents of the theorem codex into a compiled LaTeX paper and run an
LLM peer review of it. The write-up and review stages are adapted from
[SakanaAI/AI-Scientist](https://github.com/SakanaAI/AI-Scientist); see
`THIRD_PARTY_NOTICES.md` for license terms, including the mandatory
machine-generation disclosure that the bundled template embeds in every paper.

## Enable and install

The pipeline ships behind a feature flag (off by default):

```sh
thesius config set features.paper true   # or: export THESIUS_FEATURE_PAPER=1
```

```sh
pip install -e ".[paper]"        # LLM + PDF dependencies
pip install -e ".[paper-aider]"  # optional: aider-driven writeup
```

Compiling PDFs requires a LaTeX toolchain (`pdflatex`, `bibtex`); reviewing
PDFs uses `pymupdf4llm`/`pymupdf`/`pypdf` (installed by the `paper` extra).

Set your API key in the environment (`ANTHROPIC_API_KEY`, or `OPENAI_API_KEY`
for GPT models). The model defaults to `claude-opus-5` and can be changed with:

```sh
thesius config set paper.model claude-opus-5   # or THESIUS_PAPER_MODEL env var
```

## Commands

```sh
# Export a theorem's codex records (attempts, falsifications, CAS reports,
# figures) into papers/<slug>/notes.txt + results.json:
thesius paper export --theorem exact-short-box-product-fiber-curve-intersection

# Draft, refine, and compile a paper from those records:
thesius paper write --theorem exact-short-box-product-fiber-curve-intersection

# Options: --no-compile (skip pdflatex), --citations 5 (Semantic Scholar
# lookups; network required), --use-aider, --model, --out-dir, --db.

# Review a paper (PDF or plain text) and record the review in the codex:
thesius paper review papers/<slug>/<slug>.pdf --theorem <slug>
# Options: --ensemble 3 (meta-reviewed ensemble), --reflections 2, --fewshot 1.
```

`write` registers the produced PDF (kind `paper`) and `review` the review JSON
(kind `paper_review`) as codex artifacts linked to the theorem, so `thesius
status` and the Datasette/Streamlit views pick them up.

## How the writeup works

1. `codex_to_notes` exports the theorem, claims, strategy health, proof
   attempts, falsifications, computations (inlining CAS report files), and
   figure artifacts into `notes.txt`.
2. The LLM fills the theorem-paper template (Introduction, Related Work,
   Background, Conjecture-Refinement Method, Proof Attempts, CAS Verification
   Results, Falsifications, Open Questions) in one pass, then a static checker
   (missing `\end{document}`, unknown citations, missing figures, duplicate
   sections) drives up to two refinement rounds, plus a `chktex` round when
   available.
3. `pdflatex` + `bibtex` compile the result; the PDF lands in
   `papers/<slug>/<slug>.pdf`.

With `--use-aider`, the original AI-Scientist per-section SEARCH/REPLACE loop
is used instead of the single-pass draft (requires the `paper-aider` extra).
