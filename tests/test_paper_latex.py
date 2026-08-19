from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from thesius.paper.writeup import LATEX_DIR, check_latex, compile_latex

PLACEHOLDERS = {
    "TITLE HERE": "Smoke Test Paper",
    "ABSTRACT HERE": "We smoke-test the template.",
    "INTRO HERE": "Introduction text.",
    "RELATED WORK HERE": "Related work text.",
    "BACKGROUND HERE": "Background text.",
    "METHOD HERE": "Method text.",
    "ATTEMPTS HERE": "Attempts text.",
    "RESULTS HERE": "Results text.",
    "FALSIFICATIONS HERE": "Falsifications text.",
    "CONCLUSION HERE": "Conclusion text.",
}


def _filled_template() -> str:
    text = (LATEX_DIR / "template.tex").read_text()
    for placeholder, value in PLACEHOLDERS.items():
        text = text.replace(placeholder, value)
    return text


def test_template_passes_static_checks():
    text = _filled_template()
    assert check_latex(text, figures=[]) == []


@pytest.mark.skipif(
    shutil.which("pdflatex") is None or shutil.which("bibtex") is None,
    reason="LaTeX toolchain not installed",
)
def test_template_compiles_to_pdf(tmp_path: Path):
    latex_dir = tmp_path / "latex"
    latex_dir.mkdir()
    for style_file in LATEX_DIR.iterdir():
        shutil.copy(style_file, latex_dir / style_file.name)
    (latex_dir / "template.tex").write_text(_filled_template())

    pdf_path = tmp_path / "paper.pdf"
    produced = compile_latex(latex_dir, pdf_path, timeout=120)
    assert produced, "pdflatex did not produce a PDF"
    assert pdf_path.stat().st_size > 1000
