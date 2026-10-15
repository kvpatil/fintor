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

import plotly.graph_objects as go

# Validated categorical order. Assigned in fixed order, never cycled: a given
# asset class keeps its hue even when the set of classes changes.
SERIES_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300",
                "#4a3aa7", "#e34948"]
SERIES_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300",
               "#9085e9", "#e66767"]

# Diverging pair for correlation: warm/cool poles with a GREY midpoint, so zero
# reads as "nothing" rather than as another category.
DIVERGING = [[0.0, "#d03b3b"], [0.5, "#f0efec"], [1.0, "#2a78d6"]]
DIVERGING_DARK = [[0.0, "#e66767"], [0.5, "#383835"], [1.0, "#3987e5"]]

INK = "#17211d"
MUTED = "#55605b"
GRID = "rgba(23, 33, 29, 0.08)"
CONTEXT = "#9aa5a0"          # the grey that carries "context, not subject"
SURFACE = "rgba(0,0,0,0)"    # inherit the page, never paint a white box

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


def _base(fig: go.Figure, *, height: int = 320, show_legend: bool = False) -> go.Figure:
    """The house style. Every figure passes through here."""
    fig.update_layout(
        height=height,
        margin={"t": 8, "b": 8, "l": 8, "r": 8},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font={"family": BODY_FONT, "size": 13, "color": MUTED},
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
        "showgrid": True, "gridcolor": GRID, "gridwidth": 1,
        "zeroline": False, "showline": False,
        "tickfont": {"family": BODY_FONT, "size": 12, "color": MUTED},
        "title": None,
    }
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    return fig


# --- part to whole ------------------------------------------------------


def allocation_bar(weights: dict[str, float], *, height: int = 92) -> go.Figure:
    """Horizontal 100% stacked bar of asset-class weights.

    A stacked bar rather than a donut: part-to-whole is a stacked bar, and
    horizontal because the class names are long. Segments at or above 8% carry a
    direct label, which is also the relief the palette's contrast WARN requires.
    """
    folded = fold_to_max_classes(weights)
    present = [c for c in folded if c != OTHER_LABEL]
    fig = go.Figure()
    for label, pct in sorted(folded.items(), key=lambda kv: -kv[1]):
        fig.add_bar(
            y=["allocation"], x=[pct], name=label, orientation="h",
            marker={"color": hue_for_class(label, present),
                    # 2px surface gap between adjacent fills
                    "line": {"color": "#fbfaf7", "width": 2}},
            text=[f"{label} {pct:.0f}%" if pct >= 8 else ""],
            textposition="inside", insidetextanchor="middle",
            textfont={"family": BODY_FONT, "size": 12, "color": "#ffffff"},
            hovertemplate=f"{label}: %{{x:.1f}}%<extra></extra>",
        )
    _base(fig, height=height, show_legend=True)
    fig.update_layout(barmode="stack", bargap=0,
                      margin={"t": 4, "b": 4, "l": 0, "r": 0}, hovermode="closest")
    fig.update_xaxes(showgrid=False, showticklabels=False, range=[0, 100])
    fig.update_yaxes(showgrid=False, showticklabels=False)
    return fig


# --- trend over time ----------------------------------------------------


def price_with_averages(dates: Sequence[str], closes: Sequence[float],
                        ma20: Sequence[float | None], ma50: Sequence[float | None],
                        *, label: str = "Price") -> go.Figure:
    """Price as the subject, moving averages as context.

    Emphasis rather than three categorical hues: the averages are reference
    lines, not peers, and colouring them as peers would say otherwise.
    """
    fig = go.Figure()
    fig.add_scatter(x=dates, y=ma50, name="50-day average", mode="lines",
                    line={"color": CONTEXT, "width": 1.5, "dash": "dot"},
                    hovertemplate="50d %{y:,.2f}<extra></extra>")
    fig.add_scatter(x=dates, y=ma20, name="20-day average", mode="lines",
                    line={"color": CONTEXT, "width": 1.5},
                    hovertemplate="20d %{y:,.2f}<extra></extra>")
    fig.add_scatter(x=dates, y=closes, name=label, mode="lines",
                    line={"color": SERIES_LIGHT[0], "width": 2},
                    hovertemplate="%{y:,.2f}<extra></extra>")
    # Emphasised endpoint: where the series actually ends.
    if dates and closes:
        fig.add_scatter(x=[dates[-1]], y=[closes[-1]], mode="markers", name="",
                        marker={"color": SERIES_LIGHT[0], "size": 9,
                                "line": {"color": "#fbfaf7", "width": 2}},
                        showlegend=False, hoverinfo="skip")
    _base(fig, height=320, show_legend=True)
    fig.update_yaxes(tickformat=",.0f")
    return fig


def rebased_comparison(dates: Sequence[str], series: dict[str, Sequence[float]]) -> go.Figure:
    """Two indexed series on ONE axis.

    This is the answer to "compare things of different magnitude" — a second
    y-axis is the single most common charting mistake, and indexing removes the
    need for one.
    """
    fig = go.Figure()
    for i, (name, values) in enumerate(series.items()):
        fig.add_scatter(x=dates, y=values, name=name, mode="lines",
                        line={"color": SERIES_LIGHT[i % len(SERIES_LIGHT)], "width": 2},
                        hovertemplate=f"{name} %{{y:,.1f}}<extra></extra>")
    fig.add_hline(y=100, line={"color": GRID, "width": 1})
    _base(fig, height=300, show_legend=True)
    fig.update_yaxes(tickformat=",.0f", ticksuffix="")
    return fig


def projection_area(years: Sequence[int], values: Sequence[float],
                    target: float) -> go.Figure:
    """Single-series projection with the target as a reference line."""
    fig = go.Figure()
    fig.add_scatter(x=list(years), y=list(values), mode="lines", name="Projected",
                    line={"color": SERIES_LIGHT[0], "width": 2},
                    fill="tozeroy", fillcolor="rgba(42, 120, 214, 0.10)",
                    hovertemplate="year %{x}: $%{y:,.0f}<extra></extra>")
    fig.add_hline(y=target, line={"color": SERIES_LIGHT[1], "width": 1.5, "dash": "dash"},
                  annotation_text="target", annotation_position="top left",
                  annotation_font={"family": BODY_FONT, "size": 12, "color": MUTED})
    _base(fig, height=300)
    fig.update_yaxes(tickformat="$,.0f")
    fig.update_xaxes(title=None, dtick=1)
    return fig


# --- the one ClarityFI does not have ------------------------------------


def correlation_heatmap(symbols: Sequence[str], matrix: Sequence[Sequence[float]]) -> go.Figure:
    """Pairwise correlation, diverging around a grey zero.

    Diverging because the scale has a meaningful midpoint: 0 is "unrelated", and
    +1 and -1 are opposites rather than extremes of one magnitude. Every cell is
    labelled, so the reading never depends on colour alone.
    """
    fig = go.Figure(
        go.Heatmap(
            z=matrix, x=list(symbols), y=list(symbols),
            colorscale=DIVERGING, zmid=0, zmin=-1, zmax=1,
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
                font={"family": BODY_FONT, "size": 12,
                      "color": "#ffffff" if abs(value) > 0.55 else INK},
            )
    _base(fig, height=60 + 46 * len(symbols))
    fig.update_layout(hovermode="closest")
    fig.update_xaxes(showgrid=False, side="bottom")
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig
