"""LLM peer review of a paper (PDF or text).

Adapted from ai_scientist/perform_review.py in SakanaAI/AI-Scientist (The AI
Scientist Source Code License v1.0 — see THIRD_PARTY_NOTICES.md). The
NeurIPS-style review form, ensembling, meta-review, and reflection logic are
kept; numpy is replaced with statistics, PDF libraries are imported lazily,
and few-shot examples are vendored under fewshot_examples/.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Optional

from .llm import (
    extract_json_between_markers,
    get_batch_responses_from_llm,
    get_response_from_llm,
)

FEWSHOT_DIR = Path(__file__).parent / "fewshot_examples"

reviewer_system_prompt_base = (
    "You are an expert researcher reviewing a paper that was submitted to a "
    "prestigious research venue. Be critical and cautious in your decision."
)

reviewer_system_prompt_neg = (
    reviewer_system_prompt_base
    + " If a paper is bad or you are unsure, give it bad scores and reject it."
)
reviewer_system_prompt_pos = (
    reviewer_system_prompt_base
    + " If a paper is good or you are unsure, give it good scores and accept it."
)

template_instructions = """
Respond in the following format:

THOUGHT:
<THOUGHT>

REVIEW JSON:
```json
<JSON>
```

In <THOUGHT>, first briefly discuss your intuitions and reasoning for the evaluation.
Detail your high-level arguments, necessary choices and desired outcomes of the review.
Do not make generic comments here, but be specific to your current paper.
Treat this as the note-taking phase of your review.

In <JSON>, provide the review in JSON format with the following fields in the order:
- "Summary": A summary of the paper content and its contributions.
- "Strengths": A list of strengths of the paper.
- "Weaknesses": A list of weaknesses of the paper.
- "Originality": A rating from 1 to 4 (low, medium, high, very high).
- "Quality": A rating from 1 to 4 (low, medium, high, very high).
- "Clarity": A rating from 1 to 4 (low, medium, high, very high).
- "Significance": A rating from 1 to 4 (low, medium, high, very high).
- "Questions": A set of clarifying questions to be answered by the paper authors.
- "Limitations": A set of limitations and potential negative societal impacts of the work.
- "Ethical Concerns": A boolean value indicating whether there are ethical concerns.
- "Soundness": A rating from 1 to 4 (poor, fair, good, excellent).
- "Presentation": A rating from 1 to 4 (poor, fair, good, excellent).
- "Contribution": A rating from 1 to 4 (poor, fair, good, excellent).
- "Overall": A rating from 1 to 10 (very strong reject to award quality).
- "Confidence": A rating from 1 to 5 (low, medium, high, very high, absolute).
- "Decision": A decision that has to be one of the following: Accept, Reject.

For the "Decision" field, don't use Weak Accept, Borderline Accept, Borderline Reject, or Strong Reject. Instead, only use Accept or Reject.
This JSON will be automatically parsed, so ensure the format is precise.
"""

review_form = (
    """
## Review Form
Below is a description of the questions you will be asked on the review form for each paper and some guidelines on what to consider when answering these questions.

1. Summary: Briefly summarize the paper and its contributions. This is not the place to critique the paper; the authors should generally agree with a well-written summary.
  - Strengths and Weaknesses: Please provide a thorough assessment of the strengths and weaknesses of the paper, touching on each of the following dimensions:
  - Originality: Are the tasks or methods new? Is the work a novel combination of well-known techniques? Is it clear how this work differs from previous contributions? Is related work adequately cited?
  - Quality: Is the submission technically sound? Are claims well supported (e.g., by proofs, rigorous arguments, or computational verification)? Are the methods used appropriate? Is this a complete piece of work or work in progress? Are the authors careful and honest about evaluating both the strengths and weaknesses of their work?
  - Clarity: Is the submission clearly written? Is it well organized? Does it adequately inform the reader?
  - Significance: Are the results important? Are others likely to use the ideas or build on them? Does the submission address a difficult problem in a better way than previous work?

2. Questions: Please list up and carefully describe any questions and suggestions for the authors, especially where a response could change your opinion or clarify a confusion.

3. Limitations: Have the authors adequately addressed the limitations of their work? Authors should be rewarded rather than punished for being up front about limitations — including the gap between computational evidence and proof.

4. Ethical concerns: If there are ethical issues with this paper, please flag the paper for an ethics review.

5. Soundness: Please assign the paper a numerical rating on the following scale to indicate the soundness of the technical claims and methodology, and whether the central claims are adequately supported.
  4: excellent
  3: good
  2: fair
  1: poor

6. Presentation: Please assign the paper a numerical rating on the following scale to indicate the quality of the presentation — writing style, clarity, and contextualization relative to prior work.
  4: excellent
  3: good
  2: fair
  1: poor

7. Contribution: Please assign the paper a numerical rating on the following scale to indicate the quality of the overall contribution. Are the questions important? Does the paper bring significant originality of ideas or execution? Are the results valuable to share?
  4: excellent
  3: good
  2: fair
  1: poor

8. Overall: Please provide an "overall score" for this submission. Choices:
  10: Award quality: Technically flawless paper with groundbreaking impact, with no unaddressed ethical considerations.
  9: Very Strong Accept: Technically flawless paper with groundbreaking impact and flawless evaluation and reproducibility.
  8: Strong Accept: Technically strong paper with novel ideas and excellent impact, evaluation, and reproducibility.
  7: Accept: Technically solid paper with high impact on at least one sub-area, with good-to-excellent evaluation and reproducibility.
  6: Weak Accept: Technically solid, moderate-to-high impact paper with no major concerns.
  5: Borderline accept: Technically solid paper where reasons to accept outweigh reasons to reject. Use sparingly.
  4: Borderline reject: Technically solid paper where reasons to reject outweigh reasons to accept. Use sparingly.
  3: Reject: For instance, a paper with technical flaws, weak evaluation, or incompletely addressed ethical considerations.
  2: Strong Reject: Major technical flaws, poor evaluation, limited impact.
  1: Very Strong Reject: Trivial results or unaddressed ethical considerations.

9. Confidence: Please provide a "confidence score" for your assessment. Choices:
  5: Absolutely certain; very familiar with the related work and checked the details carefully.
  4: Confident but not absolutely certain.
  3: Fairly confident; possible that some parts were misunderstood or unfamiliar.
  2: Willing to defend, but quite likely some central parts were misunderstood.
  1: An educated guess.
"""
    + template_instructions
)

SCORE_LIMITS: list[tuple[str, tuple[int, int]]] = [
    ("Originality", (1, 4)),
    ("Quality", (1, 4)),
    ("Clarity", (1, 4)),
    ("Significance", (1, 4)),
    ("Soundness", (1, 4)),
    ("Presentation", (1, 4)),
    ("Contribution", (1, 4)),
    ("Overall", (1, 10)),
    ("Confidence", (1, 5)),
]

reviewer_reflection_prompt = """In your thoughts, first carefully consider the accuracy and soundness of the review you just created.
Include any other factors that you think are important in evaluating the paper.
Ensure the review is clear and concise, and the JSON is in the correct format.
Do not make things overly complicated.
In the next attempt, try and refine and improve your review.
Stick to the spirit of the original review unless there are glaring issues.

Respond in the same format as before:
THOUGHT:
<THOUGHT>

REVIEW JSON:
```json
<JSON>
```

If there is nothing to improve, simply repeat the previous JSON EXACTLY after the thought and include "I am done" at the end of the thoughts but before the JSON.
ONLY INCLUDE "I am done" IF YOU ARE MAKING NO MORE CHANGES."""

meta_reviewer_system_prompt = """You are an Area Chair at a research venue.
You are in charge of meta-reviewing a paper that was reviewed by {reviewer_count} reviewers.
Your job is to aggregate the reviews into a single meta-review in the same format.
Be critical and cautious in your decision, find consensus, and respect the opinion of all the reviewers."""


def perform_review(
    text: str,
    model: str,
    client: Any,
    num_reflections: int = 1,
    num_fs_examples: int = 1,
    num_reviews_ensemble: int = 1,
    temperature: Optional[float] = None,
    reviewer_system_prompt: str = reviewer_system_prompt_neg,
    review_instruction_form: str = review_form,
) -> dict[str, Any]:
    """Review paper text and return the parsed review dict."""
    if num_fs_examples > 0:
        base_prompt = review_instruction_form + get_review_fewshot_examples(
            num_fs_examples
        )
    else:
        base_prompt = review_instruction_form

    base_prompt += f"""
Here is the paper you are asked to review:
```
{text}
```"""

    if num_reviews_ensemble > 1:
        llm_reviews, msg_histories = get_batch_responses_from_llm(
            base_prompt,
            client,
            model,
            reviewer_system_prompt,
            temperature=temperature,
            n_responses=num_reviews_ensemble,
        )
        parsed_reviews = []
        for idx, rev in enumerate(llm_reviews):
            parsed = extract_json_between_markers(rev)
            if parsed is not None:
                parsed_reviews.append(parsed)
            else:
                print(f"Ensemble review {idx} could not be parsed; skipping.")
        if not parsed_reviews:
            raise RuntimeError("No ensemble review could be parsed.")
        review = get_meta_review(model, client, parsed_reviews)
        if review is None:
            review = parsed_reviews[0]
        for score, (lo, hi) in SCORE_LIMITS:
            scores = [
                r[score]
                for r in parsed_reviews
                if isinstance(r.get(score), (int, float)) and lo <= r[score] <= hi
            ]
            if scores:
                review[score] = int(round(statistics.mean(scores)))
        msg_history = msg_histories[0][:-1] + [
            {
                "role": "assistant",
                "content": (
                    "THOUGHT:\nI will start by aggregating the opinions of "
                    f"{num_reviews_ensemble} reviewers that I previously obtained.\n\n"
                    "REVIEW JSON:\n```json\n" + json.dumps(review) + "\n```"
                ),
            }
        ]
    else:
        llm_review, msg_history = get_response_from_llm(
            base_prompt,
            client,
            model,
            reviewer_system_prompt,
            temperature=temperature,
        )
        review = extract_json_between_markers(llm_review)
        if review is None:
            raise RuntimeError("Failed to parse the review JSON from the model output.")

    for _ in range(max(0, num_reflections - 1)):
        text_out, msg_history = get_response_from_llm(
            reviewer_reflection_prompt,
            client,
            model,
            reviewer_system_prompt,
            msg_history=msg_history,
            temperature=temperature,
        )
        reflected = extract_json_between_markers(text_out)
        if reflected is not None:
            review = reflected
        if "I am done" in text_out:
            break

    return review


def get_meta_review(
    model: str, client: Any, reviews: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    """Aggregate individual reviews into one meta-review."""
    review_text = "".join(
        f"\nReview {i + 1}/{len(reviews)}:\n```\n{json.dumps(r)}\n```\n"
        for i, r in enumerate(reviews)
    )
    llm_review, _ = get_response_from_llm(
        review_form + review_text,
        client,
        model,
        meta_reviewer_system_prompt.format(reviewer_count=len(reviews)),
    )
    return extract_json_between_markers(llm_review)


def load_paper(path: str | Path, num_pages: Optional[int] = None, min_size: int = 100) -> str:
    """Load paper text from a PDF (pymupdf4llm → pymupdf → pypdf) or a text file."""
    path = Path(path)
    if path.suffix.lower() != ".pdf":
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) < min_size:
            raise RuntimeError(f"Paper text too short: {path}")
        return text

    errors: list[str] = []
    try:
        import pymupdf4llm

        if num_pages is None:
            text = pymupdf4llm.to_markdown(str(path))
        else:
            text = pymupdf4llm.to_markdown(str(path), pages=list(range(num_pages)))
        if len(text) >= min_size:
            return text
        errors.append("pymupdf4llm produced too little text")
    except Exception as exc:
        errors.append(f"pymupdf4llm: {exc}")

    try:
        import pymupdf

        doc = pymupdf.open(str(path))
        pages = doc if num_pages is None else doc[:num_pages]
        text = "".join(page.get_text() for page in pages)
        if len(text) >= min_size:
            return text
        errors.append("pymupdf produced too little text")
    except Exception as exc:
        errors.append(f"pymupdf: {exc}")

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = reader.pages if num_pages is None else reader.pages[:num_pages]
        text = "".join(page.extract_text() for page in pages)
        if len(text) >= min_size:
            return text
        errors.append("pypdf produced too little text")
    except Exception as exc:
        errors.append(f"pypdf: {exc}")

    raise RuntimeError(
        "Could not extract text from the PDF. Install the paper extras "
        '(pip install -e ".[paper]"). Errors: ' + "; ".join(errors)
    )


def get_review_fewshot_examples(num_fs_examples: int = 1) -> str:
    """Build the few-shot prompt from vendored example papers and reviews."""
    names = ["132_automated_relational", "attention", "2_carpe_diem"]
    fewshot_prompt = """
Below are some sample reviews, copied from previous machine learning conferences.
Note that while each review is formatted differently according to each reviewer's style, the reviews are well-structured and therefore easy to navigate.
"""
    for name in names[:num_fs_examples]:
        paper_text = (FEWSHOT_DIR / f"{name}.txt").read_text(encoding="utf-8")
        review_json = json.loads((FEWSHOT_DIR / f"{name}.json").read_text(encoding="utf-8"))
        fewshot_prompt += (
            f"\nPaper:\n\n```\n{paper_text}\n```\n\n"
            f"Review:\n\n```\n{review_json['review']}\n```\n"
        )
    return fewshot_prompt
