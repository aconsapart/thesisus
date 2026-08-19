"""Generate a LaTeX paper from exported codex notes.

Adapted from ai_scientist/perform_writeup.py in SakanaAI/AI-Scientist (The AI
Scientist Source Code License v1.0 — see THIRD_PARTY_NOTICES.md). The default
path drafts the paper with direct LLM calls (no aider); an optional aider path
reproduces the original per-section SEARCH/REPLACE loop when aider-chat is
installed. Section tips are re-targeted from ML experiments to theorem and
conjecture-refinement research.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from ..db import add_artifact, connect
from .export import codex_to_notes
from .llm import (
    create_client,
    extract_json_between_markers,
    extract_latex_document,
    get_response_from_llm,
    resolve_model,
)

LATEX_DIR = Path(__file__).parent / "latex"

WRITER_SYSTEM_PROMPT = (
    "You are a mathematician writing up the current state of a research program "
    "on an open problem. You write honest, precise papers: every claim must be "
    "supported by the research notes you are given, failed attempts and "
    "falsifications are reported as such, and computational (CAS) evidence is "
    "clearly distinguished from proof. Never invent results, computations, or "
    "numerical values that are not in the notes."
)

per_section_tips = {
    "Abstract": """
- TL;DR of the research program: the target statement, the refinement method, and what was established, falsified, or left open.
- One continuous paragraph, no line breaks.
- State clearly whether the main statement is proved, conditional, computational, heuristic, or open.
""",
    "Introduction": """
- What is the target theorem/conjecture and why does it matter?
- Why is it hard? What is the overall attack plan (the strategy portfolio)?
- List the concrete contributions as bullet points: partial results, verified computations, falsified approaches, and sharpened conjectures.
""",
    "Related Work": """
- Prior work on this problem and its neighbors: how do published approaches differ in assumptions or method?
- Compare and contrast; do not merely summarize. Only cite entries present in references.bib.
""",
    "Background": """
- Definitions, notation, and prior results needed to read the paper.
- Include a formal Problem Setting subsection stating the target statement precisely, with any non-standard hypotheses highlighted.
""",
    "Method": """
- The conjecture-refinement process: how strategies were generated, ranked, attacked, and falsified.
- Describe the roles of proof attempts, falsification records, and CAS verification in the loop.
""",
    "Attempts": """
- A faithful account of the proof attempts from the notes: which strategy each used, what it established, and where it stopped.
- Report statuses honestly (PROVED / CONDITIONAL / COMPUTATIONAL / HEURISTIC / FAILED-OPEN / FALSIFIED).
""",
    "Results": """
- Computational and CAS verification results only, exactly as recorded in the notes; never invent numbers.
- Reference the available figures where they support the text, and fill in all captions.
- State the limits of computational evidence explicitly.
""",
    "Falsifications": """
- The obstructions and counterexamples from the notes, with severity.
- Explain what each falsification rules out and how it redirected the program.
""",
    "Conclusion": """
- Brief recap of the state of the program.
- Open questions and the most promising next steps, grounded in the notes.
""",
}

error_list = """- Unenclosed math symbols
- Only reference figures that exist in the directory
- LaTeX syntax errors
- Results or numbers that do not come from the research notes
- Repeatedly defined figure labels
- References to papers that are not in the references.bib block; do not add new bib entries yourself
- Unnecessary verbosity or repetition, unclear text
- Duplicate headers or duplicated \\end{document}
- Unescaped symbols, e.g. underscores in text mode
- Incorrectly closed environments
"""

DRAFT_PROMPT = """Below are (1) research notes exported from a theorem codex and (2) a LaTeX template with placeholder sections.

Write the complete paper by filling in every placeholder in the template. Requirements:
- Keep the preamble, the filecontents references.bib block, the Disclosure paragraph, and the bibliography commands exactly as they are.
- Fill in the title and every section. Section guidance:
{tips}
- Cite only entries already present in references.bib, using \\cite or \\citep.
- The available figure files are: {figures}. Include each relevant one at most once with \\includegraphics and a filled-in caption; if there are no figures, remove the example figure environment.
- Base every claim on the notes; report failed and falsified approaches honestly.

Research notes:
```
{notes}
```

LaTeX template:
```latex
{template}
```

Return the complete final template.tex inside one ```latex code fence."""

def _refine_prompt(problems: str, draft: str) -> str:
    # Built by concatenation, not str.format: error_list and drafts contain
    # literal braces (e.g. \end{document}) that .format would choke on.
    return (
        "Your draft has the following problems:\n"
        + problems
        + "\n\nAlso re-check for the following errors:\n"
        + error_list
        + "\nReturn the corrected, complete template.tex inside one ```latex "
        "code fence. Do not remove content unless it is wrong or duplicated.\n\n"
        "Current draft:\n```latex\n" + draft + "\n```"
    )


def _tips_block() -> str:
    return "\n".join(
        f"  {name}:{tips}" for name, tips in per_section_tips.items()
    )


def check_latex(latex_text: str, figures: list[str]) -> list[str]:
    """Static checks on a drafted document; returns a list of problem strings."""
    # Ignore commented-out LaTeX (e.g. the template's example figure block).
    latex_text = re.sub(r"(?<!\\)%.*", "", latex_text)
    problems: list[str] = []
    if "\\end{document}" not in latex_text:
        problems.append("Missing \\end{document} — the file is incomplete.")

    bib_match = re.search(
        r"\\begin\{filecontents\}(?:\[[^\]]*\])?\{references.bib\}(.*?)\\end\{filecontents\}",
        latex_text,
        re.DOTALL,
    )
    bib_text = bib_match.group(1) if bib_match else ""
    if not bib_match:
        problems.append("The filecontents references.bib block was removed.")
    cites = [
        c.strip()
        for group in re.findall(r"\\cite[a-z]*(?:\[[^\]]*\])*\{([^}]*)\}", latex_text)
        for c in group.split(",")
    ]
    for cite in sorted(set(cites)):
        if cite and cite not in bib_text:
            problems.append(f"Citation '{cite}' has no entry in references.bib.")

    for fig in re.findall(r"\\includegraphics.*?\{(.*?)\}", latex_text):
        if fig not in figures:
            problems.append(
                f"Figure '{fig}' is referenced but not available; available figures: {figures or 'none'}."
            )

    sections = re.findall(r"\\section\{([^}]*)\}", latex_text)
    for dup in {s for s in sections if sections.count(s) > 1}:
        problems.append(f"Duplicate section header: {dup}.")

    if "PLACEHOLDER" in latex_text or "FILL IN" in latex_text.upper() or re.search(
        r"\b[A-Z]{3,}(?: [A-Z]{3,})* HERE\b", latex_text
    ):
        problems.append("Placeholder text (e.g. 'TITLE HERE') is still present.")

    if "\\paragraph{Disclosure" not in latex_text:
        problems.append(
            "The mandatory Disclosure paragraph was removed. Restore it verbatim: "
            "it disclosing machine generation is a license requirement."
        )
    return problems


def run_chktex(tex_path: Path) -> str:
    """Run chktex if available; returns its output (empty string otherwise)."""
    if shutil.which("chktex") is None:
        return ""
    try:
        result = subprocess.run(
            ["chktex", str(tex_path), "-q", "-n2", "-n24", "-n13", "-n1"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError):
        # chktex is an optional lint step; never let it kill the pipeline.
        return ""
    return result.stdout.strip()


def compile_latex(cwd: Path, pdf_file: Path, timeout: int = 60) -> bool:
    """Compile template.tex in cwd with pdflatex/bibtex; move the PDF to pdf_file.

    Returns True if a PDF was produced. Raises RuntimeError when pdflatex is
    not installed.
    """
    if shutil.which("pdflatex") is None:
        raise RuntimeError(
            "pdflatex not found. Install a LaTeX toolchain (e.g. MacTeX or "
            "TeX Live) to compile papers, or rerun with --no-compile."
        )
    commands = [
        ["pdflatex", "-interaction=nonstopmode", "template.tex"],
        ["bibtex", "template"],
        ["pdflatex", "-interaction=nonstopmode", "template.tex"],
        ["pdflatex", "-interaction=nonstopmode", "template.tex"],
    ]
    for command in commands:
        if command[0] == "bibtex" and shutil.which("bibtex") is None:
            continue
        try:
            subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            print(f"LaTeX timed out after {timeout} seconds: {' '.join(command)}")
    produced = cwd / "template.pdf"
    if produced.is_file():
        shutil.move(str(produced), str(pdf_file))
        return True
    return False


# --- Citation lookup (Semantic Scholar), optional -------------------------

CITATION_SYSTEM_MSG = """You are helping add missing citations to a mathematics paper draft. You will identify one needed citation and a search query for it; then select the best match from search results. Only propose citations substantiated by the draft's content. Do not propose a citation that already exists in references.bib."""

CITATION_FIRST_PROMPT = """Round {round} of {total}. Here is the current draft:

```latex
{draft}
```

Identify the most important missing citation and a search query to find it.
If no more citations are needed, reply with the exact phrase "No more citations needed".
Otherwise respond in this JSON format inside a ```json fence:
{{"Description": "where and how to add the citation", "Query": "search query"}}"""

CITATION_SECOND_PROMPT = """The search returned these papers:

{papers}

Select the best matches (or none). Respond in this JSON format inside a ```json fence:
{{"Selected": "[0]", "Description": "updated description of the edit"}}
"Selected" is a JSON list of result indices as a string, "[]" if none fit."""

CITATION_APPLY_PROMPT = """These BibTeX entries were appended to the references.bib filecontents block:

```
{bibtex}
```

Apply this edit to the draft: {description}

Use \\cite or \\citep with the exact keys from the entries above. Return the complete updated template.tex inside one ```latex code fence.

Current draft:
```latex
{draft}
```"""


def search_for_papers(query: str, result_limit: int = 10) -> list[dict[str, Any]]:
    """Search Semantic Scholar. Returns [] on failure or no results."""
    import requests

    if not query:
        return []
    try:
        rsp = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            headers={"X-API-KEY": os.environ["S2_API_KEY"]}
            if os.environ.get("S2_API_KEY")
            else {},
            params={
                "query": query,
                "limit": result_limit,
                "fields": "title,authors,venue,year,abstract,citationStyles,citationCount",
            },
            timeout=30,
        )
        rsp.raise_for_status()
        results = rsp.json()
        time.sleep(1.0)
        if not results.get("total"):
            return []
        return results.get("data", [])
    except Exception as exc:  # network failures must not kill the writeup
        print(f"Semantic Scholar lookup failed: {exc}")
        return []


def add_citations(
    draft: str, client: Any, model: str, num_rounds: int
) -> str:
    """Optionally enrich the draft with citations found via Semantic Scholar."""
    for round_num in range(num_rounds):
        text, msg_history = get_response_from_llm(
            CITATION_FIRST_PROMPT.format(
                round=round_num + 1, total=num_rounds, draft=draft
            ),
            client, model, CITATION_SYSTEM_MSG,
        )
        if "No more citations needed" in text:
            break
        parsed = extract_json_between_markers(text)
        if not parsed or "Query" not in parsed:
            continue
        papers = search_for_papers(parsed["Query"])
        if not papers:
            continue
        papers_str = "\n\n".join(
            f"{i}: {p.get('title')}. {p.get('venue')}, {p.get('year')}.\n"
            f"Abstract: {(p.get('abstract') or '')[:500]}"
            for i, p in enumerate(papers)
        )
        # Keep the first-round conversation so the selection sees the draft
        # and the proposed edit, as in the original.
        text, _ = get_response_from_llm(
            CITATION_SECOND_PROMPT.format(papers=papers_str),
            client, model, CITATION_SYSTEM_MSG, msg_history=msg_history,
        )
        parsed = extract_json_between_markers(text)
        if not parsed:
            continue
        selected = str(parsed.get("Selected", "[]")).strip("[] ")
        if not selected:
            continue
        try:
            indices = [int(i) for i in selected.split(",")]
            bibtexs = [papers[i]["citationStyles"]["bibtex"] for i in indices]
        except (ValueError, IndexError, KeyError, TypeError):
            continue
        bibtex_string = "\n".join(bibtexs)
        draft = draft.replace(
            "\\end{filecontents}", f"{bibtex_string}\n\\end{{filecontents}}", 1
        )
        text, _ = get_response_from_llm(
            CITATION_APPLY_PROMPT.format(
                bibtex=bibtex_string,
                description=parsed.get("Description", "integrate the new citations"),
                draft=draft,
            ),
            client, model, CITATION_SYSTEM_MSG, max_tokens=64000,
        )
        updated = extract_latex_document(text)
        if updated:
            draft = updated
    return draft


# --- Orchestration ---------------------------------------------------------


def write_paper(
    db_path: str,
    theorem_slug: str,
    out_dir: str | Path,
    model: Optional[str] = None,
    citation_rounds: int = 0,
    max_refine_rounds: int = 2,
    compile_pdf: bool = True,
    use_aider: bool = False,
) -> dict[str, Any]:
    """Export codex data, draft the paper, validate/refine, and compile.

    Returns a dict with the produced paths. Registers the PDF (or .tex) as a
    codex artifact linked to the theorem.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Fail soft on a missing LaTeX toolchain BEFORE spending any LLM calls.
    if compile_pdf and shutil.which("pdflatex") is None:
        print(
            "pdflatex not found; the paper will be drafted but not compiled. "
            "Install a LaTeX toolchain to produce PDFs."
        )
        compile_pdf = False

    con = connect(db_path)
    try:
        export = codex_to_notes(con, theorem_slug, out)
    finally:
        con.close()

    latex_out = out / "latex"
    latex_out.mkdir(exist_ok=True)
    for style_file in LATEX_DIR.iterdir():
        shutil.copy(style_file, latex_out / style_file.name)
    template_text = (latex_out / "template.tex").read_text(encoding="utf-8")

    model_id = resolve_model(model)
    client, model_id = create_client(model_id)
    notes = export["notes_path"].read_text(encoding="utf-8")
    figures = export["figures"]

    if use_aider:
        draft = _write_with_aider(latex_out, notes, model_id)
    else:
        response, _ = get_response_from_llm(
            DRAFT_PROMPT.format(
                tips=_tips_block(),
                figures=figures or "none",
                notes=notes,
                template=template_text,
            ),
            client, model_id, WRITER_SYSTEM_PROMPT, max_tokens=64000,
        )
        draft = extract_latex_document(response)
        if draft is None:
            raise RuntimeError("The model did not return a complete LaTeX document.")

    def refine(current: str, rounds: int) -> str:
        for _ in range(rounds):
            problems = check_latex(current, figures)
            if not problems:
                break
            response, _ = get_response_from_llm(
                _refine_prompt("\n".join(f"- {p}" for p in problems), current),
                client, model_id, WRITER_SYSTEM_PROMPT, max_tokens=64000,
            )
            refined = extract_latex_document(response)
            if refined is None:
                break
            current = refined
        return current

    draft = refine(draft, max_refine_rounds)

    if citation_rounds > 0:
        draft = add_citations(draft, client, model_id, citation_rounds)
        # The citation stage rewrites the whole document; re-validate it.
        draft = refine(draft, max_refine_rounds)

    tex_path = latex_out / "template.tex"
    tex_path.write_text(draft, encoding="utf-8")

    chktex_output = run_chktex(tex_path)
    if chktex_output:
        response, _ = get_response_from_llm(
            _refine_prompt(f"chktex reported:\n{chktex_output}", draft),
            client, model_id, WRITER_SYSTEM_PROMPT, max_tokens=64000,
        )
        refined = extract_latex_document(response)
        if refined:
            draft = refined
            tex_path.write_text(draft, encoding="utf-8")

    pdf_path = out / f"{theorem_slug}.pdf"
    pdf_produced = False
    if compile_pdf:
        # Remove files generated by a previous compile so a stale
        # references.bib can never shadow the entries in this draft.
        for stale in ("references.bib", "template.pdf", "template.bbl", "template.aux"):
            stale_path = latex_out / stale
            if stale_path.exists():
                stale_path.unlink()
        pdf_produced = compile_latex(latex_out, pdf_path)

    artifact_path = pdf_path if pdf_produced else tex_path
    con = connect(db_path)
    try:
        add_artifact(
            con,
            path=str(artifact_path),
            kind="paper" if pdf_produced else "paper_tex",
            theorem_slug=theorem_slug,
            description_md=f"Generated paper for {theorem_slug} (model {model_id}).",
        )
    finally:
        con.close()

    return {
        "tex_path": tex_path,
        "pdf_path": pdf_path if pdf_produced else None,
        "notes_path": export["notes_path"],
        "results_path": export["results_path"],
        "model": model_id,
    }


def _write_with_aider(latex_out: Path, notes: str, model_id: str) -> str:
    """Original AI-Scientist-style per-section writeup driven by aider."""
    try:
        from aider.coders import Coder
        from aider.io import InputOutput
        from aider.models import Model
    except ImportError as exc:
        raise RuntimeError(
            "aider-chat is not installed. Install it with: "
            'pip install -e ".[paper-aider]", or rerun without --use-aider.'
        ) from exc

    notes_path = latex_out / "notes.txt"
    notes_path.write_text(notes, encoding="utf-8")
    tex_path = latex_out / "template.tex"
    io = InputOutput(yes=True, chat_history_file=str(latex_out / "aider_history.txt"))
    coder = Coder.create(
        main_model=Model(model_id),
        fnames=[str(tex_path), str(notes_path)],
        io=io,
        stream=False,
        use_git=False,
        edit_format="diff",
    )
    coder.run(
        "We are filling in latex/template.tex from the research notes in "
        "notes.txt. First fill in the Title and Abstract sections.\n"
        f"Tips:\n{per_section_tips['Abstract']}\n"
        "Use *SEARCH/REPLACE* blocks to perform the edits."
    )
    for section in ["Introduction", "Background", "Related Work", "Method",
                    "Attempts", "Results", "Falsifications", "Conclusion"]:
        coder.run(
            f"Please fill in the {section} section of the writeup from the "
            f"notes. Tips:\n{per_section_tips[section]}\n"
            "Only cite entries already in references.bib. "
            "Use *SEARCH/REPLACE* blocks to perform the edits."
        )
    coder.run(
        "Criticize and refine the whole draft. Fix any of these errors:\n"
        + error_list
        + "\nUse *SEARCH/REPLACE* blocks to perform the edits."
    )
    return tex_path.read_text(encoding="utf-8")
