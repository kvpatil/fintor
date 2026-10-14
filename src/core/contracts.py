"""Pydantic contracts: the only data shapes permitted to cross a layer boundary.

Keeping these in one module is what makes the dependency rule in
.github/copilot-instructions.md enforceable - every layer depends on these shapes
rather than on each other's internals.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


# --- enumerations -------------------------------------------------------


class Intent(StrEnum):
    """Routable agent intents, in canonical synthesis order."""

    PORTFOLIO = "portfolio"
    GOAL_PLANNING = "goal_planning"
    MARKET = "market"
    NEWS = "news"
    TAX = "tax"
    FINANCE_QA = "finance_qa"


class RouterTier(StrEnum):
    """Which escalation tier resolved the route. Tiers 1-2 cost nothing."""

    RULES = "rules"              # tier 1: regex + entity signals
    EMBEDDING = "embedding"      # tier 2: k-NN against intent centroids
    LLM = "llm"                  # tier 3: structured-output classifier
    LLM_FALLBACK_RULES = "llm_fallback_rules"  # tier 3 errored, tier 1 result used


class Difficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ModelTier(StrEnum):
    CHEAP = "cheap"
    STRONG = "strong"


class CacheTier(StrEnum):
    """Which cache layer served a response. MISS means a provider was called."""

    MISS = "miss"
    EXACT = "exact"              # layer 1
    SEMANTIC = "semantic"        # layer 2 (Phase 2)
    PROMPT = "prompt"            # layer 3 (Phase 2)
    OFFLINE = "offline"          # FINTOR_OFFLINE: canned, never billed


class DataStatus(StrEnum):
    """Provenance of market/news data. Anything but LIVE must be disclosed."""

    LIVE = "live"
    CACHED = "cached"
    STALE = "stale"
    SAMPLE = "sample"            # synthetic; never used to value a portfolio


# --- personas -----------------------------------------------------------


class Holding(BaseModel):
    symbol: str
    shares: float
    cost_basis: float | None = None
    asset_class: str = "equity"


class Goal(BaseModel):
    name: str
    target_amount: float
    current_savings: float = 0.0
    monthly_contribution: float = 0.0
    years: float = 5.0
    assumed_return_pct: float = 0.0  # 0% default: we never imply a forecast


class Persona(BaseModel):
    """A synthetic teaching profile. Never a real account - see finance-compliance."""

    id: str
    name: str
    age: int
    headline: str                       # one-line descriptor for the selector
    experience_level: Difficulty
    risk_tolerance: str                 # conservative | moderate | aggressive
    horizon_years: int
    cash: float = 0.0
    holdings: list[Holding] = Field(default_factory=list)
    goals: list[Goal] = Field(default_factory=list)
    journey_prompts: list[str] = Field(default_factory=list)

    @property
    def thread_id(self) -> str:
        """Per-persona checkpointer thread, so conversations stay isolated."""
        return f"persona::{self.id}"


# --- retrieval ----------------------------------------------------------


class RetrievedChunk(BaseModel):
    """One candidate passage. Ranks are kept so AI Internals can show the fusion."""

    id: str
    text: str
    title: str = ""
    category: str = ""
    difficulty: Difficulty | None = None
    source_name: str = ""
    source_url: str = ""
    score: float = 0.0               # cosine, recomputed after fusion
    dense_rank: int | None = None
    sparse_rank: int | None = None
    rrf_score: float = 0.0
    retrieval: str = ""              # dense | sparse | dense+sparse
    rerank_delta: int | None = None  # Phase 2


class Citation(BaseModel):
    index: int                       # the [n] marker shown to the user
    title: str
    source_name: str = ""
    source_url: str = ""
    category: str = ""
    excerpt: str = ""
    score: float = 0.0


# --- market & news ------------------------------------------------------


class Quote(BaseModel):
    symbol: str
    price: float
    change_pct: float | None = None
    currency: str = "USD"
    provider: str = ""
    status: DataStatus = DataStatus.LIVE
    as_of: datetime | None = None
    notice: str | None = None        # set whenever status is not LIVE


class NewsItem(BaseModel):
    title: str
    source: str = ""
    url: str = ""
    published: datetime | None = None
    summary: str = ""
    status: DataStatus = DataStatus.LIVE


# --- routing, agents, cost ---------------------------------------------


class Query(BaseModel):
    text: str
    persona_id: str | None = None
    top_k: int = 3
    category: str | None = None
    difficulty_ceiling: Difficulty | None = None  # set from the persona
    history: list[dict[str, str]] = Field(default_factory=list)


class RouteDecision(BaseModel):
    intents: list[Intent]
    tier: RouterTier
    reason: str = ""
    advice_request: bool = False
    confident: bool = True
    signals: dict[str, list[str]] = Field(default_factory=dict)


class CostRecord(BaseModel):
    """One billable (or cache-served) model call. Aggregated by the cost meter."""

    provider: str
    model: str
    tier: ModelTier = ModelTier.CHEAP
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    usd: float = 0.0
    latency_ms: int = 0
    cache_tier: CacheTier = CacheTier.MISS
    persona_id: str | None = None
    fallback_used: bool = False


class AgentResult(BaseModel):
    """What one agent contributes. Errors are contained here, never raised upward."""

    agent: str
    intent: Intent
    text: str = ""
    citations: list[Citation] = Field(default_factory=list)
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    data_status: DataStatus = DataStatus.LIVE
    notices: list[str] = Field(default_factory=list)
    narration: str = "llm"           # llm | template (grounding fallback)
    error_code: str | None = None
    latency_ms: int = 0
    costs: list[CostRecord] = Field(default_factory=list)
