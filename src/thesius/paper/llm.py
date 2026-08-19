"""Minimal LLM client layer for the paper pipeline.

Adapted from ai_scientist/llm.py in SakanaAI/AI-Scientist (The AI Scientist
Source Code License v1.0 — see THIRD_PARTY_NOTICES.md). Trimmed to the two
provider families Thesius supports (Anthropic and OpenAI) and updated for
current Anthropic models: no sampling parameters, streaming for long outputs,
and explicit handling of the ``refusal`` stop reason.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from ..settings import get_setting

DEFAULT_MODEL = "claude-opus-5"
# On current Claude models thinking is on by default and counts against
# max_tokens, so the budget needs headroom beyond the visible response.
DEFAULT_MAX_TOKENS = 16000

MISSING_ANTHROPIC = (
    "The 'anthropic' package is required for the paper pipeline. "
    'Install it with: pip install -e ".[paper]"'
)
MISSING_OPENAI = (
    "The 'openai' package is required to use GPT/o-series models. "
    "Install it with: pip install openai"
)


def resolve_model(cli_model: Optional[str] = None) -> str:
    """Resolve the model id: --model flag, then paper.model config, then env."""
    if cli_model:
        return cli_model
    configured = get_setting("paper.model")
    if isinstance(configured, str) and configured.strip():
        return configured
    return os.environ.get("THESIUS_PAPER_MODEL", DEFAULT_MODEL)


def create_client(model: str) -> tuple[Any, str]:
    """Create an API client for the given model id.

    Returns (client, model). Providers are imported lazily so the core CLI
    works without the optional 'paper' dependencies installed.
    """
    if model.startswith("claude"):
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(MISSING_ANTHROPIC) from exc
        return anthropic.Anthropic(), model
    if model.startswith(("gpt", "o1", "o3", "o4")):
        try:
            import openai
        except ImportError as exc:
            raise RuntimeError(MISSING_OPENAI) from exc
        return openai.OpenAI(), model
    raise ValueError(f"Unsupported model for the paper pipeline: {model}")


def get_response_from_llm(
    msg: str,
    client: Any,
    model: str,
    system_message: str,
    msg_history: Optional[list[dict[str, Any]]] = None,
    temperature: Optional[float] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> tuple[str, list[dict[str, Any]]]:
    """Send one message and return (response_text, new_msg_history).

    ``temperature`` is ignored for Claude models: current Anthropic models
    reject sampling parameters.
    """
    if msg_history is None:
        msg_history = []

    if model.startswith("claude"):
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system_message,
            messages=new_msg_history,
        ) as stream:
            response = stream.get_final_message()
        if response.stop_reason == "refusal":
            raise RuntimeError(
                "The model declined this request (stop_reason=refusal). "
                "Rephrase the content or try a different model."
            )
        if response.stop_reason == "max_tokens":
            raise RuntimeError(
                f"The response was truncated at max_tokens={max_tokens} "
                "(thinking counts against this budget). Retry with a larger "
                "max_tokens."
            )
        content = "".join(
            block.text for block in response.content if block.type == "text"
        )
    elif model.startswith("gpt"):
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        kwargs: dict[str, Any] = {}
        if temperature is not None:
            kwargs["temperature"] = temperature
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_message}, *new_msg_history],
            max_completion_tokens=max_tokens,
            n=1,
            **kwargs,
        )
        content = response.choices[0].message.content
    elif model.startswith(("o1", "o3", "o4")):
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": system_message}, *new_msg_history],
            max_completion_tokens=max_tokens,
            n=1,
        )
        content = response.choices[0].message.content
    else:
        raise ValueError(f"Unsupported model: {model}")

    return content, new_msg_history + [{"role": "assistant", "content": content}]


def get_batch_responses_from_llm(
    msg: str,
    client: Any,
    model: str,
    system_message: str,
    msg_history: Optional[list[dict[str, Any]]] = None,
    temperature: Optional[float] = None,
    n_responses: int = 1,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> tuple[list[str], list[list[dict[str, Any]]]]:
    """Collect n independent responses to the same message (for ensembling)."""
    contents: list[str] = []
    histories: list[list[dict[str, Any]]] = []
    for _ in range(n_responses):
        content, history = get_response_from_llm(
            msg,
            client,
            model,
            system_message,
            msg_history=list(msg_history) if msg_history else None,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        contents.append(content)
        histories.append(history)
    return contents, histories


def extract_json_between_markers(llm_output: str) -> Optional[dict[str, Any]]:
    """Extract the first valid JSON object from ```json fences (or bare braces)."""
    for json_string in re.findall(r"```json(.*?)```", llm_output, re.DOTALL):
        json_string = json_string.strip()
        try:
            return json.loads(json_string)
        except json.JSONDecodeError:
            try:
                cleaned = re.sub(r"[\x00-\x1F\x7F]", "", json_string)
                return json.loads(cleaned)
            except json.JSONDecodeError:
                continue
    # Fallback: decode balanced objects starting at each '{' so nested JSON
    # is handled (a lazy regex would stop at the first '}').
    decoder = json.JSONDecoder()
    for idx, char in enumerate(llm_output):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(llm_output[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def extract_latex_document(llm_output: str) -> Optional[str]:
    """Extract a complete LaTeX document from an LLM response.

    Prefers ```latex fenced blocks, then falls back to the span from
    \\documentclass through \\end{document}.
    """
    for fence in ("```latex", "```tex", "```"):
        pattern = re.escape(fence) + r"\n(.*?)```"
        match = re.search(pattern, llm_output, re.DOTALL)
        if match and "\\documentclass" in match.group(1):
            return match.group(1).strip()
    match = re.search(r"(\\documentclass.*\\end\{document\})", llm_output, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None
