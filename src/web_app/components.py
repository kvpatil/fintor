"""Shared render helpers. Pages render; they never contain business logic."""

from __future__ import annotations

import html
import re
from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st

from src.web_app.theme import chip

# Main column to rail. 7:3 at the 1120px measure puts charts at ~750px and the
# rail at ~320px - wide enough for a number and a sentence, narrow enough that
# it never competes with the main column for attention.
RAIL_RATIO = [7, 3]

# "live" is a state, not the brand: it takes the same green as the nav dot and
# as --fin-up, so one app has one green that means "good".
STATUS_LABEL = {"live": ("Live data", "good"), "cached": ("Saved copy", ""),
                "stale": ("Last known", "warn"), "sample": ("SAMPLE DATA", "warn")}


# --- rendering model output ---------------------------------------------


def escape_dollars(text: str) -> str:
    r"""Escape bare dollar signs so Streamlit stops reading money as maths.

    Use this for ANY string with two currency amounts that reaches st.markdown,
    st.progress(text=...) or a chat message - it has now bitten three separate
    surfaces (a metric value, an answer, and the budget bar).

    Observed live, in an answer about a portfolio:

        "worth about $90,184, including $12,000 in cash"

    Streamlit's markdown treats a `$...$` pair as inline LaTeX, so everything
    between the two amounts rendered as a maths span - the figures came out in
    a serif italic and the sentence broke apart. Any answer quoting two
    currency amounts hits this, which for a finance assistant is most of them.

    Escaping is safe here because Fintor's agents write prose and currency, not
    TeX; an already-escaped `\$` is left alone so this stays idempotent.
    """
    return re.sub(r"(?<!\\)\$", r"\\$", text)


def persona_card(persona) -> None:
    """The active reader, shown in the page body that needs it.

    Lives here rather than in the chrome because it is context for an answer, not
    navigation - and because the gate already established who you are.
    """
    st.markdown(
        f'<div class="fin-persona"><b>{persona.name}, {persona.age}</b> '
        f'<span>&middot; {persona.headline}</span><br>'
        f'<span>{persona.experience_level.value} &middot; {persona.risk_tolerance} risk '
        f'&middot; {persona.horizon_years}-year horizon &middot; '
        f'a teaching example, not a real account</span></div>',
        unsafe_allow_html=True,
    )


def persona_line(persona) -> None:
    """One-line variant for the data pages, where the card would be noise."""
    st.caption(
        f"{persona.name}, {persona.age} · {persona.headline} · "
        f"{persona.experience_level.value} · states {persona.risk_tolerance} risk. "
        f"A teaching example, not a real account."
    )


def data_status_chip(status: str) -> str:
    label, kind = STATUS_LABEL.get(status, (status, ""))
    return chip(label, kind)


def citations_block(citations: list[dict]) -> None:
    if not citations:
        return
    seen = set()
    with st.expander(f"Sources ({len(citations)})", expanded=False):
        for c in citations:
            key = (c.get("title"), c.get("source_url"))
            if key in seen:
                continue
            seen.add(key)
            url, title = c.get("source_url", ""), c.get("title", "")
            name = c.get("source_name", "")
            line = f"**[{c['index']}] {title}** — {name}"
            if url:
                line += f" · [source]({url})"
            st.markdown(line)
            if c.get("excerpt"):
                st.caption(c["excerpt"])


def cost_bar(meter) -> None:
    s = meter.summary()
    spent, budget = s["spent_usd"], s["budget_usd"]
    frac = min(1.0, spent / budget) if budget else 0.0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Session spend", f"${spent:.5f}")
    c2.metric("Budget left", f"${s['remaining_usd']:.5f}")
    c3.metric("Model calls", s["calls"])
    c4.metric("Cache hits", f"{s['cache_hits']} ({s['hit_rate']:.0%})")
    st.progress(frac,
                text=escape_dollars(f"${spent:.5f} of ${budget:.2f} session budget"))
    if meter.near_limit:
        st.warning("Approaching the session budget. Set FINTOR_OFFLINE=1 to keep working for free.")


# --- surfaces -----------------------------------------------------------


def main_and_rail():
    """The two-column workspace: results on the left, controls and context right.

    A single stacked column reads as a document. Putting the inputs and the
    secondary numbers in a rail is what makes a page read as an instrument you
    operate - and it is the structural difference that no amount of chart
    polish was going to close.

    Read the rail FIRST when it holds inputs. The columns are created here in
    visual order, so a `with rail:` block that runs before `with main:` still
    renders on the right; it just means the main column can use the values.
    """
    return st.columns(RAIL_RATIO, gap="large")


@contextmanager
def card(key: str, *, title: str = "", subtitle: str = "", tag: str = "",
         tag_kind: str = "", meta_label: str = "", meta_value: str = "") -> Iterator[None]:
    """A bordered surface with an optional header.

    `st.container(border=True, key=...)` rather than a wrapper div: Streamlit
    renders its elements OUTSIDE any HTML we emit, which is why the old
    `.gate-wrap` max-width never applied to anything. The key becomes a
    `st-key-card-*` class, which is a stable hook the theme can style.
    """
    with st.container(border=True, key=f"card-{key}"):
        head = ""
        if tag:
            head += f'<div class="fin-card-tag">{chip(tag, tag_kind)}</div>'
        left = ""
        if title:
            left += f'<div class="fin-card-title">{html.escape(title)}</div>'
        if subtitle:
            left += f'<div class="fin-card-sub">{subtitle}</div>'
        right = ""
        if meta_value:
            right = ('<div class="fin-card-meta">'
                     f'<span>{html.escape(meta_label)}</span>'
                     f'<b>{html.escape(meta_value)}</b></div>')
        if left or right:
            head += f'<div class="fin-card-head"><div>{left}</div>{right}</div>'
        if head:
            st.markdown(head, unsafe_allow_html=True)
        yield


def what_this_shows(*points: str, ignores: str) -> None:
    """Plain-language notes under a figure.

    `ignores` is keyword-only and REQUIRED, which is the point: a chart that
    explains itself but not its limits is the more dangerous of the two. Every
    figure in Fintor states what it leaves out, and the signature is what makes
    that impossible to forget rather than merely encouraged.
    """
    if not ignores.strip():
        raise ValueError("every figure must state what it ignores")
    items = "".join(f"<li>{p}</li>" for p in points)
    st.markdown(
        '<div class="fin-note"><div class="fin-note-title">What this shows</div>'
        f'<ul>{items}<li class="fin-note-limit">{ignores}</li></ul></div>',
        unsafe_allow_html=True,
    )


def rail_stat(label: str, value: str, note: str = "", tone: str = "") -> None:
    """One big number with its name and an optional sentence, for the rail."""
    cls = f"fin-rail-value fin-tone-{tone}" if tone else "fin-rail-value"
    body = (f'<div class="fin-rail-label">{html.escape(label)}</div>'
            f'<div class="{cls}">{html.escape(value)}</div>')
    if note:
        body += f'<div class="fin-rail-note">{note}</div>'
    st.markdown(body, unsafe_allow_html=True)


def rail_rows(rows: list[tuple[str, str, str]]) -> None:
    """Compact label / value / delta list - the rail's answer to a KPI row.

    Four `st.metric` tiles in a 320px rail wrap into illegible slivers; the same
    information reads fine as rows.
    """
    out = ['<div class="fin-rail-rows">']
    for label, value, delta in rows:
        tone = ""
        if delta.startswith("+"):
            tone = " fin-up"
        elif delta.startswith("-"):
            tone = " fin-down"
        out.append(f'<div class="fin-rail-row"><span>{html.escape(label)}</span>'
                   f'<b>{html.escape(value)}</b>'
                   f'<em class="fin-delta{tone}">{html.escape(delta)}</em></div>')
    out.append("</div>")
    st.markdown("".join(out), unsafe_allow_html=True)
