from __future__ import annotations

from thesius.paper.llm import (
    extract_json_between_markers,
    extract_latex_document,
    resolve_model,
)
from thesius.paper.writeup import _refine_prompt, check_latex

VALID_DOC = r"""\documentclass{article}
\begin{filecontents}[overwrite]{references.bib}
@article{lu2024aiscientist, title={T}, author={A}, year={2024}}
\end{filecontents}
\begin{document}
\section{Introduction}
Text \citep{lu2024aiscientist}.
\paragraph{Disclosure.}
Machine generated.
\end{document}"""


def test_refine_prompt_survives_latex_braces():
    # Regression: building this with str.format raised KeyError('document')
    # because error_list contains a literal \end{document}.
    prompt = _refine_prompt("- a problem", VALID_DOC)
    assert "\\end{document}" in prompt
    assert "a problem" in prompt


def test_check_latex_accepts_valid_document():
    assert check_latex(VALID_DOC, figures=[]) == []


def test_check_latex_detects_problems():
    assert any(
        "end{document}" in p
        for p in check_latex(VALID_DOC.replace("\\end{document}", ""), [])
    )
    assert any(
        "no entry" in p
        for p in check_latex(VALID_DOC.replace("lu2024aiscientist}.", "unknown2020}."), [])
    )
    with_fig = VALID_DOC.replace(
        "Text", "\\includegraphics{missing.png} Text"
    )
    assert any("missing.png" in p for p in check_latex(with_fig, []))
    assert check_latex(with_fig, ["missing.png"]) == []

    duplicated = VALID_DOC.replace(
        "\\section{Introduction}",
        "\\section{Introduction}\nx\n\\section{Introduction}",
    )
    assert any("Duplicate section" in p for p in check_latex(duplicated, []))

    assert any(
        "Placeholder" in p for p in check_latex(VALID_DOC.replace("Text", "INTRO HERE"), [])
    )
    assert any(
        "Disclosure" in p
        for p in check_latex(VALID_DOC.replace("\\paragraph{Disclosure.}", ""), [])
    )


def test_check_latex_ignores_comments_and_optional_cite_args():
    commented = VALID_DOC.replace(
        "Text", "% \\includegraphics{ghost.png}\nText"
    )
    assert check_latex(commented, []) == []

    optional = VALID_DOC.replace(
        "\\citep{lu2024aiscientist}", "\\citep[e.g.][]{lu2024aiscientist}"
    )
    assert check_latex(optional, []) == []
    bad_optional = optional.replace("lu2024aiscientist}.", "unknown2020}.")
    assert any("no entry" in p for p in check_latex(bad_optional, []))


def test_extract_latex_document():
    fenced = f"Here you go:\n```latex\n{VALID_DOC}\n```\nDone."
    assert extract_latex_document(fenced) == VALID_DOC
    assert extract_latex_document(VALID_DOC) == VALID_DOC
    assert extract_latex_document("no latex here") is None


def test_extract_json_handles_nested_objects_without_fence():
    text = 'Sure: {"Summary": "ok", "Scores": {"Overall": 5}} hope that helps'
    parsed = extract_json_between_markers(text)
    assert parsed == {"Summary": "ok", "Scores": {"Overall": 5}}
    assert extract_json_between_markers("nothing structured") is None


def test_resolve_model_precedence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("THESIUS_PAPER_MODEL", raising=False)
    assert resolve_model("cli-model") == "cli-model"
    assert resolve_model() == "claude-opus-5"
    monkeypatch.setenv("THESIUS_PAPER_MODEL", "env-model")
    assert resolve_model() == "env-model"
    from thesius.settings import set_setting

    set_setting("paper.model", "config-model")
    assert resolve_model() == "config-model"
