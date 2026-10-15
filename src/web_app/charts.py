"""One figure factory, so every chart in Fintor reads as the same system.

Nothing in `views/` should construct a Plotly figure directly — a test enforces
that. The point is not tidiness: it is that a page which builds its own figure
drifts off the palette, loses tabular axis labels, and quietly reintroduces
default Plotly blue.

The palette is the validated reference instance from the dataviz skill, checked
with `scripts/validate_palette.js` against Fintor's own surfaces rather than
assumed:

    light #fbfaf7 — all checks pass, with one WARN: three hues fall under 3:1
                    contrast, which obligates visible labels or a table view.
                    Hence direct labels on segments, and the holdings table.
    dark  #121714 — all checks pass, contrast included.

Three deliberate departures from what ClarityFI does:

* Allocation is a **horizontal stacked bar, not a donut**. Part-to-whole is a
  stacked bar; a donut asks the reader to compare angles, which is the thing
  people are worst at. The total moves to a hero figure where it reads instantly.
* Price and its moving averages use **emphasis** — one hue for the subject, grey
  for context — rather than three competing colours.
* Benchmark comparison is **indexed to 100 on one axis**, never a second y-axis.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

import plotly.graph_objects as go

from src.web_app.labels import asset_class

# Validated categorical order. Assigned in fixed order, never cycled: a given
# asset class keeps its hue even when the set of classes changes.
SERIES_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300",
                "#4a3aa7", "#e34948"]
SERIES_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300",
               "#9085e9", "#e66767"]

# Diverging pair for correlation: warm/cool poles with a GREY midpoint, so zero
# reads as "nothing" rather than as another category.
#
# The poles are LIGHTER than the categorical blue and red, and that is the whole
# point: every cell carries its value as text, so the deepest fill still has to
# clear 4.5:1 against the label. Measured, not guessed -
#   #2a78d6 (categorical blue) vs ink  -> 3.74:1  FAIL
#   #4689d9 (this pole)        vs ink  -> 4.59:1  pass
#   #d03b3b (categorical red)  vs ink  -> below   FAIL
#   #d76160 (this pole)        vs ink  -> 4.54:1  pass
# Those are the deepest steps toward each hue that still pass, so the ramp gives
# up as little saturation as the contrast requirement allows.
# The dark ramp is NOT the light one inverted - it is stepped from the dark
# surface outward and measured the same way, against light ink:
#   #396ba7 vs #e8eae8 -> 4.53:1   #9d5352 vs #e8eae8 -> 4.58:1
DIVERGING = [[0.0, "#d76160"], [0.5, "#f0efec"], [1.0, "#4689d9"]]
DIVERGING_DARK = [[0.0, "#9d5352"], [0.5, "#383835"], [1.0, "#396ba7"]]

INK = "#17211d"
MUTED = "#55605b"
GRID = "rgba(23, 33, 29, 0.08)"
CONTEXT = "#9aa5a0"          # the grey that carries "context, not subject"
SURFACE = "rgba(0,0,0,0)"    # inherit the page, never paint a white box

INK_DARK = "#e8eae8"
MUTED_DARK = "#9aa5a0"
GRID_DARK = "rgba(232, 234, 232, 0.10)"
CONTEXT_DARK = "#6b746f"
PAPER_LIGHT = "#fbfaf7"      # used only for the hairline between adjacent fills
PAPER_DARK = "#121714"

BODY_FONT = "Inter Tight, system-ui, sans-serif"


# Canonical asset-class order. Hue is assigned by position in THIS list among the
# classes present, never by weight: re-weighting a portfolio must not repaint it.
CLASS_ORDER = ["equity", "bond", "cash", "international", "single_stock",
               "crypto", "reit"]

# Only FOUR categorical hues, and specifically these four. Measured with
# scripts/validate_palette.js --pairs all on #fbfaf7:
#   blue/orange/aqua/violet          -> ALL CHECKS PASS
#   any five-hue set tried           -> FAILED
#   the default first-five           -> magenta vs orange normal-vision dE 12.9,
#                                       below the 15 floor. That is a hard fail;
#                                       the skill is explicit that labels and
#                                       texture do NOT excuse it.
# Adjacency in a stacked bar shifts with the weights, so all-pairs is the honest
# test rather than the adjacent pairlist.
ALLOCATION_HUES = ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"]
MAX_CLASSES = len(ALLOCATION_HUES)

# "Other" is a bucket, not an identity, so it takes a neutral rather than a
# categorical slot - it must not read as a fifth competing class.
OTHER_HUE = "#8a948f"
OTHER_LABEL = "other"


def palette(n: int = 8) -> list[str]:
    """First `n` categorical hues, in fixed order."""
    return SERIES_LIGHT[:n]


def fold_to_max_classes(weights: dict[str, float]) -> dict[str, float]:
    """Keep the largest MAX_CLASSES classes; sum the rest into "other".

    Four is not a style choice - it is the largest set of these hues that clears
    the normal-vision floor on every pair. Nothing is lost: the holdings table
    below the chart still lists every class by name.
    """
    if len(weights) <= MAX_CLASSES:
        return dict(weights)
    ranked = sorted(weights.items(), key=lambda kv: -kv[1])
    kept = dict(ranked[:MAX_CLASSES - 1])
    kept[OTHER_LABEL] = round(sum(v for _k, v in ranked[MAX_CLASSES - 1:]), 2)
    return kept


def hue_for_class(name: str, present: list[str] | None = None) -> str:
    """Hue for an asset class, ordered by CLASS_ORDER among those present.

    Keyed to the class rather than to its rank, so the colours hold still when
    the weights move.
    """
    if name == OTHER_LABEL:
        return OTHER_HUE
    ordered = [c for c in CLASS_ORDER if c in (present or CLASS_ORDER)]
    try:
        return ALLOCATION_HUES[ordered.index(name) % len(ALLOCATION_HUES)]
    except ValueError:
        return OTHER_HUE


class Scheme(NamedTuple):
    """The handful of values that differ between light and dark.

    Dark is *selected*, not an automatic flip: its series hues and its diverging
    ramp are stepped against the dark surface and validated there, because a
    light-mode hue inverted onto a dark ground either glares or disappears.
    """

    series: list[str]
    diverging: list[list]
    ink: str
    muted: str
    grid: str
    context: str
    paper: str


LIGHT = Scheme(SERIES_LIGHT, DIVERGING, INK, MUTED, GRID, CONTEXT, PAPER_LIGHT)
DARK = Scheme(SERIES_DARK, DIVERGING_DARK, INK_DARK, MUTED_DARK, GRID_DARK,
              CONTEXT_DARK, PAPER_DARK)


def scheme(dark: bool = False) -> Scheme:
    return DARK if dark else LIGHT


def _base(fig: go.Figure, *, height: int = 320, show_legend: bool = False,
          sc: Scheme = LIGHT) -> go.Figure:
    """The house style. Every figure passes through here."""
    fig.update_layout(
        height=height,
        margin={"t": 8, "b": 8, "l": 8, "r": 8},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font={"family": BODY_FONT, "size": 13, "color": sc.muted},
        showlegend=show_legend,
        legend={"orientation": "h", "y": -0.18, "x": 0, "font": {"size": 13},
                # follow trace order so the legend reads in the same order as
                # the marks; Plotly otherwise sorts it and the two disagree
                "traceorder": "normal"},
        hoverlabel={"font": {"family": BODY_FONT, "size": 13}},
        # Crosshair + tooltip is the default for a chart that can carry one.
        hovermode="x unified",
    )
    # Recessive grid and axes; digits line up in columns.
    axis = {
        "showgrid": True, "gridcolor": sc.grid, "gridwidth": 1,
        "zeroline": False, "showline": False,
        "tickfont": {"family": BODY_FONT, "size": 12, "color": sc.muted},
        "title": None,
    }
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    return fig


# --- part to whole ------------------------------------------------------


def allocation_bar(weights: dict[str, float], *, height: int = 92,
                   dark: bool = False) -> go.Figure:
    """Horizontal 100% stacked bar of asset-class weights.

    A stacked bar rather than a donut: part-to-whole is a stacked bar, and
    horizontal because the class names are long. Segments at or above 8% carry a
    direct label, which is also the relief the palette's contrast WARN requires.
    """
    sc = scheme(dark)
    folded = fold_to_max_classes(weights)
    present = [c for c in folded if c != OTHER_LABEL]
    fig = go.Figure()
    for key, pct in sorted(folded.items(), key=lambda kv: -kv[1]):
        label = asset_class(key)
        fig.add_bar(
            y=["allocation"], x=[pct], name=label, orientation="h",
            marker={"color": hue_for_class(key, present),
                    # 2px surface gap between adjacent fills
                    "line": {"color": sc.paper, "width": 2}},
            text=[f"{label} {pct:.0f}%" if pct >= 8 else ""],
            textposition="inside", insidetextanchor="middle",
            textfont={"family": BODY_FONT, "size": 12, "color": "#ffffff"},
            hovertemplate=f"{label}: %{{x:.1f}}%<extra></extra>",
        )
    _base(fig, height=height, show_legend=True, sc=sc)
    fig.update_layout(barmode="stack", bargap=0,
                      margin={"t": 4, "b": 4, "l": 0, "r": 0}, hovermode="closest")
    fig.update_xaxes(showgrid=False, showticklabels=False, range=[0, 100])
    fig.update_yaxes(showgrid=False, showticklabels=False)
    return fig


# --- trend over time ----------------------------------------------------


def price_with_averages(dates: Sequence[str], closes: Sequence[float],
                        ma20: Sequence[float | None], ma50: Sequence[float | None],
                        *, label: str = "Price", dark: bool = False) -> go.Figure:
    """Price as the subject, moving averages as context.

    Emphasis rather than three categorical hues: the averages are reference
    lines, not peers, and colouring them as peers would say otherwise.
    """
    sc = scheme(dark)
    fig = go.Figure()
    fig.add_scatter(x=dates, y=ma50, name="50-day average", mode="lines",
                    line={"color": sc.context, "width": 1.5, "dash": "dot"},
                    hovertemplate="50d %{y:,.2f}<extra></extra>")
    fig.add_scatter(x=dates, y=ma20, name="20-day average", mode="lines",
                    line={"color": sc.context, "width": 1.5},
                    hovertemplate="20d %{y:,.2f}<extra></extra>")
    fig.add_scatter(x=dates, y=closes, name=label, mode="lines",
                    line={"color": sc.series[0], "width": 2},
                    hovertemplate="%{y:,.2f}<extra></extra>")
    # Emphasised endpoint: where the series actually ends.
    if dates and closes:
        fig.add_scatter(x=[dates[-1]], y=[closes[-1]], mode="markers", name="",
                        marker={"color": sc.series[0], "size": 9,
                                "line": {"color": sc.paper, "width": 2}},
                        showlegend=False, hoverinfo="skip")
    _base(fig, height=320, show_legend=True, sc=sc)
    fig.update_yaxes(tickformat=",.0f")
    return fig


def rebased_comparison(dates: Sequence[str], series: dict[str, Sequence[float]],
                       *, dark: bool = False) -> go.Figure:
    """Two indexed series on ONE axis.

    This is the answer to "compare things of different magnitude" — a second
    y-axis is the single most common charting mistake, and indexing removes the
    need for one.
    """
    sc = scheme(dark)
    fig = go.Figure()
    for i, (name, values) in enumerate(series.items()):
        fig.add_scatter(x=dates, y=values, name=name, mode="lines",
                        line={"color": sc.series[i % len(sc.series)], "width": 2},
                        hovertemplate=f"{name} %{{y:,.1f}}<extra></extra>")
    fig.add_hline(y=100, line={"color": sc.grid, "width": 1})
    _base(fig, height=300, show_legend=True, sc=sc)
    fig.update_yaxes(tickformat=",.0f", ticksuffix="")
    return fig


def projection_area(years: Sequence[int], values: Sequence[float],
                    target: float, *, dark: bool = False) -> go.Figure:
    """Single-series projection with the target as a reference line.

    The target rule is recessive ink, NOT a categorical hue. It was orange, which
    is "bond" on the Portfolio page and reads as a warning everywhere else - a
    reference line is not a second series and must not be painted like one.
    """
    sc = scheme(dark)
    fill = "rgba(57, 135, 229, 0.16)" if dark else "rgba(42, 120, 214, 0.10)"
    fig = go.Figure()
    fig.add_scatter(x=list(years), y=list(values), mode="lines", name="Projected",
                    line={"color": sc.series[0], "width": 2},
                    fill="tozeroy", fillcolor=fill,
                    hovertemplate="year %{x}: $%{y:,.0f}<extra></extra>")
    fig.add_hline(y=target, line={"color": sc.muted, "width": 1.5, "dash": "dash"},
                  annotation_text=f"target ${target:,.0f}",
                  annotation_position="top left",
                  annotation_font={"family": BODY_FONT, "size": 12, "color": sc.muted})
    _base(fig, height=300, sc=sc)
    fig.update_yaxes(tickformat="$,.0f")
    fig.update_xaxes(title=None, dtick=1)
    return fig


# --- the one ClarityFI does not have ------------------------------------


def correlation_heatmap(symbols: Sequence[str], matrix: Sequence[Sequence[float]],
                        *, dark: bool = False) -> go.Figure:
    """Pairwise correlation, diverging around a grey zero.

    Diverging because the scale has a meaningful midpoint: 0 is "unrelated", and
    +1 and -1 are opposites rather than extremes of one magnitude. Every cell is
    labelled, so the reading never depends on colour alone.

    Every label takes the SAME ink. The previous rule flipped to white above
    |r| 0.55, which was guessed rather than measured and was backwards: at r=0.57
    the fill is #7fabdf, where white scores 2.39:1 and ink scores 6.91:1. Because
    the ramp's poles are now capped at a step that ink clears (see DIVERGING),
    one colour is correct for every cell and there is no threshold to get wrong.
    """
    sc = scheme(dark)
    fig = go.Figure(
        go.Heatmap(
            z=matrix, x=list(symbols), y=list(symbols),
            colorscale=sc.diverging, zmid=0, zmin=-1, zmax=1,
            xgap=2, ygap=2,  # 2px surface gap between cells
            colorbar={"thickness": 10, "outlinewidth": 0, "tickfont": {"size": 12},
                      "tickvals": [-1, 0, 1], "ticktext": ["-1", "0", "+1"]},
            hovertemplate="%{y} vs %{x}: %{z:.2f}<extra></extra>",
        )
    )
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            fig.add_annotation(
                x=symbols[j], y=symbols[i], text=f"{value:.2f}", showarrow=False,
                font={"family": BODY_FONT, "size": 12, "color": sc.ink},
            )
    _base(fig, height=60 + 46 * len(symbols), sc=sc)
    fig.update_layout(hovermode="closest")
    fig.update_xaxes(showgrid=False, side="bottom")
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig
