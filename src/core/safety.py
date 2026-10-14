"""Disclaimers, the advice redirect, and the harmful-content short-circuit.

Education, not advice, is a graded requirement and a real regulatory boundary.
See .github/skills/finance-compliance/SKILL.md. The disclaimer text lives here and
nowhere else so it cannot drift or be appended twice.
"""

from __future__ import annotations

import re
import unicodedata

EDUCATIONAL_DISCLAIMER = (
    "This is general financial education, not personal financial, investment, legal or tax "
    "advice. Figures shown are illustrative."
)

ADVICE_REDIRECT = (
    "I can't tell you what to buy or sell — but I can explain the mechanics behind the "
    "decision so you can weigh it yourself."
)

MARKET_DATA_NOTE = (
    "Prices and historical returns describe the past. They are not forecasts."
)

SAMPLE_DATA_NOTE = "Sample data, not real market data."

PERSONA_NOTE = "This is a teaching example, not a real account."

NO_ANSWER = (
    "I don't have a grounded answer for that in my knowledge base, and I'd rather say so than "
    "guess. Try asking about a specific concept — for example diversification, capital gains, "
    "or how an HSA works."
)

SELF_HARM_RESPONSE = (
    "It sounds like you may be going through something very difficult, and that matters more "
    "than any financial question.\n\n"
    "If you are in the US, you can call or text 988 to reach the Suicide and Crisis Lifeline, "
    "or text HOME to 741741 for the Crisis Text Line. Outside the US, findahelpline.com lists "
    "services by country. If you are in immediate danger, please call your local emergency "
    "number.\n\n"
    "I'm not able to help with this, but people who can are available right now."
)

# Regex heuristics only. Not a substitute for a dedicated safety classifier, and the
# code should not pretend otherwise - see the prompt-safety skill.
_SELF_HARM = re.compile(
    r"\b(kill myself|end my life|suicide|suicidal|want to die|not worth living)\b", re.I
)
_ADVICE = re.compile(
    r"\b(should i (buy|sell|invest|hold|put|move)|what should i (buy|do|invest)|"
    r"is (it|now) a good time to (buy|sell)|tell me what to (buy|invest)|"
    r"pick (a|the best) (stock|fund)|which (stock|fund) should)\b",
    re.I,
)
_INJECTION = re.compile(
    r"(ignore (all |any )?(previous|prior|above) instructions|disregard (the )?(system|above)|"
    r"reveal your (system )?prompt|you are now|</?system>|developer mode|jailbreak)",
    re.I,
)


def normalize_input(text: str, max_chars: int = 4000) -> str:
    """NFKC + strip control characters + cap length. Runs before anything else sees
    the text, so downstream matching is against a predictable shape."""
    cleaned = unicodedata.normalize("NFKC", text or "")
    cleaned = "".join(ch for ch in cleaned if ch == "\n" or not unicodedata.category(ch).startswith("C"))
    return cleaned.strip()[:max_chars]


def detect_self_harm(text: str) -> bool:
    return bool(_SELF_HARM.search(text or ""))


def looks_like_advice_request(text: str) -> bool:
    return bool(_ADVICE.search(text or ""))


def looks_like_injection(text: str) -> bool:
    """Flagged input is still answered: the defence is that prompts treat user text
    as data. Dropping the question would punish the user for a false positive."""
    return bool(_INJECTION.search(text or ""))


def ensure_educational_disclaimer(text: str) -> str:
    """Idempotent. A cached answer already carries it; appending twice looks careless."""
    body = (text or "").rstrip()
    if EDUCATIONAL_DISCLAIMER[:40] in body:
        return body
    return f"{body}\n\n_{EDUCATIONAL_DISCLAIMER}_"
