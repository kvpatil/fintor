"""Citation verification.

The prompts require inline [n] markers, but a model can emit [4] when only three
passages were supplied. Nothing downstream would notice, so we check: every marker
must resolve to a citation that was actually retrieved for this answer. Unresolvable
markers are stripped and counted.

The benchmark project mandates citations and never verifies them. This is the gap.
"""

from __future__ import annotations

import re

from src.core.contracts import AgentResult

_MARKER = re.compile(r"\[(\d{1,2})\]")


def verify_citations(text: str, valid_indices: set[int]) -> tuple[str, list[int]]:
    """Returns (cleaned_text, stripped_markers)."""
    stripped: list[int] = []

    def replace(match: re.Match) -> str:
        n = int(match.group(1))
        if n in valid_indices:
            return match.group(0)
        stripped.append(n)
        return ""

    cleaned = _MARKER.sub(replace, text or "")
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned)
    return cleaned.strip(), stripped


def verify_result(result: AgentResult) -> tuple[AgentResult, list[int]]:
    valid = {c.index for c in result.citations}
    if not result.text:
        return result, []
    cleaned, stripped = verify_citations(result.text, valid)
    if stripped:
        result.text = cleaned
        result.notices.append(
            f"Removed {len(stripped)} citation marker(s) that did not match a retrieved source."
        )
    return result, stripped
