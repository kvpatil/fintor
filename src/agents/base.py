"""BaseAgent: timing, cost collection, and error containment.

A failing agent must degrade the answer, not break the request. The graph fans out
to several agents, and one provider hiccup should cost the user one section, not
the whole response - so _execute may raise and run() never does.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from src.core.contracts import AgentResult, Intent, Persona, Query


class BaseAgent(ABC):
    """Subclasses implement only _execute. Everything else is uniform, which is what
    makes adding a seventh agent a one-file change."""

    name: str = "agent"
    intent: Intent = Intent.FINANCE_QA
    section_title: str = "Background"

    def __init__(self, deps) -> None:
        self.deps = deps  # the container; see core/container.py

    @abstractmethod
    async def _execute(self, query: Query, persona: Persona | None) -> AgentResult: ...

    async def run(self, query: Query, persona: Persona | None = None) -> AgentResult:
        started = time.perf_counter()
        try:
            result = await self._execute(query, persona)
        except Exception as exc:  # noqa: BLE001 - containment is the point
            result = AgentResult(
                agent=self.name,
                intent=self.intent,
                text="",
                error_code=type(exc).__name__,
                notices=[f"The {self.section_title.lower()} part could not be completed."],
            )
        result.latency_ms = int((time.perf_counter() - started) * 1000)
        return result

    # -- helpers shared by subclasses ---------------------------------------
    def _persona_preamble(self, persona: Persona | None) -> str:
        """Persona conditioning: the same corpus and the same agents produce
        different answers because the reader is different."""
        if persona is None:
            return ""
        tone = {
            "beginner": "The reader is new to investing. Define every term you use in the same "
                        "sentence, avoid jargon entirely, and keep sentences short.",
            "intermediate": "The reader knows the basics. You may use standard terms without "
                            "defining them, but explain anything beyond common vocabulary.",
            "advanced": "The reader is experienced. Be precise and concise; you may use "
                        "technical vocabulary without definition.",
        }[persona.experience_level.value]
        return (
            f"\nReader profile: {persona.name}, age {persona.age}, "
            f"{persona.experience_level.value} experience, states {persona.risk_tolerance} risk "
            f"tolerance, {persona.horizon_years}-year horizon. {tone}"
        )
