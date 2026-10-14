"""Cost metering and the session budget guard.

The guard is a kill switch, not a warning: with limited credits, a runaway loop
is the failure mode that actually hurts. Callers must not catch BudgetExceeded
and retry - surface it with the remaining budget. See the llm-cost-discipline skill.
"""

from __future__ import annotations

import threading
from collections import defaultdict

from src.core.contracts import CacheTier, CostRecord, ModelTier


class BudgetExceeded(RuntimeError):
    """Raised *before* a provider call when the ceiling would be crossed."""

    def __init__(self, spent_usd: float, budget_usd: float) -> None:
        self.spent_usd = spent_usd
        self.budget_usd = budget_usd
        super().__init__(
            f"Session budget reached: ${spent_usd:.4f} of ${budget_usd:.2f} spent. "
            f"Raise cost.session_budget_usd, or set FINTOR_OFFLINE=1 to keep working for free."
        )


def price_call(
    *,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    prices_per_mtok: dict[str, float] | None = None,
    tier: ModelTier = ModelTier.CHEAP,
    cache_tier: CacheTier = CacheTier.MISS,
    latency_ms: int = 0,
    persona_id: str | None = None,
    fallback_used: bool = False,
) -> CostRecord:
    """Build a CostRecord. Cache hits still get one, with usd == 0, so hit rate and
    savings stay measurable instead of invisible."""
    prices = prices_per_mtok or {"input": 0.0, "output": 0.0}
    billable_input = max(0, input_tokens - cached_input_tokens)
    usd = 0.0
    if cache_tier in {CacheTier.MISS, CacheTier.PROMPT}:
        usd = (billable_input / 1_000_000) * prices.get("input", 0.0) + (
            output_tokens / 1_000_000
        ) * prices.get("output", 0.0)
    return CostRecord(
        provider=provider,
        model=model,
        tier=tier,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
        usd=round(usd, 8),
        latency_ms=latency_ms,
        cache_tier=cache_tier,
        persona_id=persona_id,
        fallback_used=fallback_used,
    )


class CostMeter:
    """Accumulates CostRecords for a session and enforces the ceiling.

    Thread-safe because Streamlit reruns and the async graph can both touch it.
    """

    def __init__(self, budget_usd: float = 0.50, warn_at_fraction: float = 0.75) -> None:
        self._budget = budget_usd
        self._warn_at = warn_at_fraction
        self._records: list[CostRecord] = []
        self._lock = threading.Lock()

    # -- enforcement ---------------------------------------------------------
    def check(self) -> None:
        """Call immediately before any billable request."""
        if self.spent_usd >= self._budget:
            raise BudgetExceeded(self.spent_usd, self._budget)

    def record(self, rec: CostRecord) -> CostRecord:
        with self._lock:
            self._records.append(rec)
        return rec

    # -- reporting -----------------------------------------------------------
    @property
    def budget_usd(self) -> float:
        return self._budget

    @property
    def spent_usd(self) -> float:
        with self._lock:
            return round(sum(r.usd for r in self._records), 8)

    @property
    def remaining_usd(self) -> float:
        return max(0.0, round(self._budget - self.spent_usd, 8))

    @property
    def near_limit(self) -> bool:
        return self._budget > 0 and self.spent_usd >= self._budget * self._warn_at

    @property
    def records(self) -> list[CostRecord]:
        with self._lock:
            return list(self._records)

    def summary(self) -> dict[str, object]:
        recs = self.records
        hits = [r for r in recs if r.cache_tier is not CacheTier.MISS]
        return {
            "calls": len(recs),
            "cache_hits": len(hits),
            "hit_rate": round(len(hits) / len(recs), 3) if recs else 0.0,
            "input_tokens": sum(r.input_tokens for r in recs),
            "output_tokens": sum(r.output_tokens for r in recs),
            "spent_usd": self.spent_usd,
            "remaining_usd": self.remaining_usd,
            "budget_usd": self._budget,
            "fallbacks": sum(1 for r in recs if r.fallback_used),
            "by_tier": {t.value: sum(1 for r in recs if r.cache_tier is t) for t in CacheTier},
        }

    def by_persona(self) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for r in self.records:
            totals[r.persona_id or "unassigned"] += r.usd
        return {k: round(v, 8) for k, v in totals.items()}
