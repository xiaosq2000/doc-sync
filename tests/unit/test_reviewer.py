from __future__ import annotations

import tomllib
from pathlib import Path
from typing import cast

import pytest

from docstale.render import HOOK_GUIDANCE

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def codex_reviewer() -> dict[str, object]:
    path = _PROJECT_ROOT / ".codex/agents/docstale-reviewer.toml"
    with path.open("rb") as agent_file:
        return cast("dict[str, object]", tomllib.load(agent_file))


def test_codex_reviewer_has_explicit_model_settings(
    codex_reviewer: dict[str, object],
) -> None:
    assert codex_reviewer["model"] == "gpt-6-luna"
    assert codex_reviewer["model_reasoning_effort"] == "high"
    assert codex_reviewer["sandbox_mode"] == "read-only"
    assert isinstance(codex_reviewer["description"], str)
    assert codex_reviewer["description"]


def test_hook_guidance_names_the_codex_reviewer(
    codex_reviewer: dict[str, object],
) -> None:
    assert codex_reviewer["name"] == "docstale-reviewer"
    assert f"`{codex_reviewer['name']}`" in HOOK_GUIDANCE


def test_codex_and_claude_reviewer_instructions_match(
    codex_reviewer: dict[str, object],
) -> None:
    path = _PROJECT_ROOT / ".claude/agents/docstale-reviewer.md"
    _, separator, instructions = path.read_text(encoding="utf-8").partition("\n---\n")
    assert separator
    codex_instructions = codex_reviewer["developer_instructions"]
    assert isinstance(codex_instructions, str)
    assert codex_instructions.strip() == instructions.strip()
    assert "Do not edit files and do not run `docstale stamp`." in codex_instructions
