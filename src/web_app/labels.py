"""Human labels for machine field names.

Domain code names things for code: `single_stock`, `assumed_return_pct`,
`on_track`. Those names are correct in Python and wrong on screen — a reader
sees an underscore and knows they are looking at a database dump rather than a
product. This module is the one place that translation happens, so a chart
legend and a table header can never disagree about what a class is called.

Deliberately a lookup with a fallback rather than a generic `str.title()`: the
fallback keeps an unknown class readable, but the table pins the house spelling
for the classes Fintor actually ships ("Bonds" plural, "REITs" capitalised,
"Single stock" with a lowercase s).
"""

from __future__ import annotations

ASSET_CLASS_LABELS = {
    "equity": "Equity",
    "bond": "Bonds",
    "cash": "Cash",
    "international": "International",
    "single_stock": "Single stock",
    "crypto": "Crypto",
    "reit": "REITs",
    "other": "Other",
}


def asset_class(name: str) -> str:
    """Display name for an asset class. Unknown classes degrade readably."""
    if name in ASSET_CLASS_LABELS:
        return ASSET_CLASS_LABELS[name]
    cleaned = name.replace("_", " ").strip()
    return cleaned[:1].upper() + cleaned[1:] if cleaned else name
