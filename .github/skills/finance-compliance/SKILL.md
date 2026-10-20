---
name: finance-compliance
description: 'Keep Fintor on the education side of the education-vs-advice line: disclaimers, refusal phrasing, and what must never be generated'
---

Your goal is to help me keep Fintor firmly on the **education** side of the line between
financial education and financial advice. This is a graded requirement of the project and a
real regulatory boundary, so treat it as a hard constraint rather than a stylistic preference.

## Never generate

- **Buy/sell/hold recommendations** for any specific security, fund, or asset class — not
  even hedged ones ("you might consider buying X").
- **Price predictions or forecasts.** Historical returns and trends describe the past only.
  Never say or imply where a price is going.
- **A personal tax calculation.** Explain how a rule works; never compute what someone owes.
  Never state a specific dollar limit, rate, bracket, or threshold that is not present in the
  retrieved context — a confidently wrong number is worse than pointing to IRS.gov.
- **Allocation prescriptions** ("you should hold 60% bonds"). Explain how allocation decisions
  are commonly framed and what tradeoffs they involve.
- **Claims about the user's own situation** beyond what the active persona actually states.

## Always do

- **Append the educational disclaimer** to every user-facing answer, exactly once. Use
  `ensure_educational_disclaimer()` from `src/core/safety.py`; never hand-write the text, and
  never append it twice when a cached answer already carries it.
- **Label synthetic data honestly.** Persona portfolios are sample accounts with simulated holdings — say so.
  Mock market data must be labeled "sample data, not real" and must never be used to value a
  portfolio or narrate news as if current.
- **Disclose data provenance.** When a quote comes from cache or a stale fallback, say so with
  its age. Silence implies live data.

## When the user asks for advice

Do not refuse flatly, and do not comply. **Redirect to the mechanism**: decline the
recommendation in one sentence, then teach the framework that would inform the decision.

- Asked "should I buy NVDA?" → explain concentration risk, position sizing, and how
  diversification is commonly reasoned about; then note what the persona's own numbers show.
- Asked "is now a good time to buy?" → explain why timing is unknowable, what dollar-cost
  averaging is, and what the data does and does not tell us.

Use `ADVICE_REDIRECT` from `src/core/safety.py` for the declining sentence so the phrasing is
consistent everywhere. Set `advice_request=True` on the route decision so the synthesizer
appends it once, at the end, rather than each agent repeating it.

## Tone

Write for a capable adult who is new to this, not for a student. The brief describes
someone intimidated and afraid of making mistakes: the answer to that is clarity and
directness, not hand-holding. Plain words over jargon; when a technical term is
unavoidable, define it in the same sentence. Never condescend, never imply a question
was naive, and never adopt a classroom voice - this is a finance product, not a course.
