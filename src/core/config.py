"""Configuration: the only module in Fintor permitted to read environment variables.

Everything else receives settings as arguments, which is what keeps the layers
testable - a test can construct Settings directly instead of mutating os.environ.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
_ENV_LOADED = False


def _load_dotenv(path: Path | None = None) -> None:
    """Minimal .env reader. Deliberately not python-dotenv: we need exactly one
    behaviour (a real shell variable wins over the file) and no extra dependency."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    env_path = path or (ROOT / ".env")
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    raw: dict[str, Any] = field(repr=False)
    openai_api_key: str = field(default="", repr=False)
    anthropic_api_key: str = field(default="", repr=False)
    offline: bool = False
    session_budget_usd: float = 0.50
    # Shared password for the six demo accounts on the sign-in screen. Blank
    # means sign-in is disabled and the screen says how to enable it - see
    # core/auth.py, which fails closed rather than waving everyone through.
    demo_password: str = field(default="", repr=False)
    # Langfuse. The SDK would read these itself, but the house rule is that only
    # this module touches the environment, so they are read here and passed
    # explicitly. LANGFUSE_BASE_URL is the SDK's own current name.
    langfuse_public_key: str = field(default="", repr=False)
    langfuse_secret_key: str = field(default="", repr=False)
    langfuse_base_url: str = field(default="", repr=False)

    # -- section accessors; sections are plain dicts straight from config.yaml ----
    @property
    def llm(self) -> dict[str, Any]:
        return self.raw.get("llm", {})

    @property
    def rag(self) -> dict[str, Any]:
        return self.raw.get("rag", {})

    @property
    def cache(self) -> dict[str, Any]:
        return self.raw.get("cache", {})

    @property
    def market(self) -> dict[str, Any]:
        return self.raw.get("market", {})

    @property
    def news(self) -> dict[str, Any]:
        return self.raw.get("news", {})

    @property
    def workflow(self) -> dict[str, Any]:
        return self.raw.get("workflow", {})

    @property
    def cost(self) -> dict[str, Any]:
        return self.raw.get("cost", {})

    def model_for(self, tier: str, provider: str) -> str:
        return str(self.llm.get("tiers", {}).get(tier, {}).get(provider, ""))

    def price(self, model: str) -> dict[str, float]:
        """Per-1M-token prices. Unknown models price at zero rather than crashing a
        demo - the meter's job is visibility, not billing accuracy."""
        return self.cost.get("prices_per_mtok", {}).get(model, {"input": 0.0, "output": 0.0})

    def has_provider(self, provider: str) -> bool:
        return bool({"openai": self.openai_api_key, "anthropic": self.anthropic_api_key}.get(provider))

    def path(self, *parts: str) -> Path:
        p = ROOT.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


def load_settings(config_path: Path | None = None) -> Settings:
    _load_dotenv()
    cfg_file = config_path or (ROOT / "config.yaml")
    raw = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) if cfg_file.exists() else {}
    budget = os.environ.get("FINTOR_SESSION_BUDGET_USD")
    return Settings(
        raw=raw,
        openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
        offline=os.environ.get("FINTOR_OFFLINE", "0").strip() in {"1", "true", "True", "yes"},
        demo_password=os.environ.get("FINTOR_DEMO_PASSWORD", "").strip(),
        langfuse_public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip(),
        langfuse_secret_key=os.environ.get("LANGFUSE_SECRET_KEY", "").strip(),
        langfuse_base_url=(os.environ.get("LANGFUSE_BASE_URL")
                           or os.environ.get("LANGFUSE_HOST", "")).strip(),
        session_budget_usd=float(budget) if budget else float(raw.get("cost", {}).get("session_budget_usd", 0.50)),
    )
