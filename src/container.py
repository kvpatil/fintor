"""Composition root. Nothing else constructs its own dependencies.

Deliberately at `src/` rather than inside `src/core/`: wiring must import from
every layer, so it has to sit at the TOP of the dependency order. It lived in
`core` until test_no_upward_imports caught the inversion - the fitness function
earning its place on day one.

One place to read config and wire implementations means swapping an embedder, a
provider, or a cache backend is a config change rather than a code change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.cache import EmbeddingCache, SqliteCache
from src.core.config import Settings, load_settings
from src.core.contracts import ModelTier
from src.core.cost import CostMeter
from src.core.llm import build_chain
from src.data.market import MarketService, MockProvider, YFinanceProvider
from src.data.news import MockNews, NewsService, RssNews, YFinanceNews
from src.rag.embedding import build_embedder
from src.rag.index import NumpyIndex
from src.rag.retriever import HybridRetriever


@dataclass
class Deps:
    settings: Settings
    meter: CostMeter
    chain: Any
    embedder: Any
    retriever: Any
    market: MarketService
    news: NewsService
    router: Any
    agents: dict

    @property
    def offline(self) -> bool:
        return bool(self.settings.offline)


def build(settings: Settings | None = None, *, persona_id: str | None = None,
          tier: ModelTier = ModelTier.CHEAP) -> Deps:
    s = settings or load_settings()
    cache_dir = s.cache.get("dir", "data/cache")

    meter = CostMeter(budget_usd=s.session_budget_usd,
                      warn_at_fraction=float(s.cost.get("warn_at_fraction", 0.75)))
    llm_cache = SqliteCache(s.path(cache_dir, "llm.db"))
    chain = build_chain(s, meter, llm_cache, tier=tier, persona_id=persona_id)

    emb_cache = EmbeddingCache(s.path(cache_dir, "embeddings.db"))
    embedder = build_embedder(s, emb_cache)

    index_dir = Path(s.rag.get("index_dir", "src/data/kb/index"))
    index = NumpyIndex(embedder.dim, embedder.model_name)
    index.load(index_dir)
    chunks = json.loads((index_dir / "records.json").read_text(encoding="utf-8"))
    retriever = HybridRetriever(
        chunks, index, embedder,
        rrf_k=int(s.rag.get("rrf_k", 60)), overfetch=int(s.rag.get("overfetch", 20)),
        score_threshold=float(s.rag.get("score_threshold", 0.25)),
        mode=str(s.rag.get("mode", "hybrid")),
    )

    data_cache = SqliteCache(s.path(cache_dir, "market.db"))
    market = MarketService(
        [YFinanceProvider(), MockProvider()], data_cache,
        quote_ttl=int(s.cache.get("market_ttl_seconds", 1800)),
        history_ttl=int(s.cache.get("history_ttl_seconds", 21600)),
        stale_max_age=int(s.cache.get("stale_max_age_seconds", 604800)),
    )
    news = NewsService(
        [YFinanceNews(), RssNews(s.news.get("rss_feeds", [])), MockNews()], data_cache,
        ttl=int(s.cache.get("market_ttl_seconds", 1800)),
        stale_max_age=int(s.cache.get("stale_max_age_seconds", 604800)),
    )

    from src.agents.registry import build_agents
    from src.workflow.router import Router

    router = Router(embedder=embedder, chain=chain,
                    use_llm=bool(s.workflow.get("router_use_llm", True)))

    deps = Deps(settings=s, meter=meter, chain=chain, embedder=embedder, retriever=retriever,
                market=market, news=news, router=router, agents={})
    deps.agents = build_agents(deps)
    return deps
