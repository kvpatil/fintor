"""The pre-auth About shell: the reference pages, readable without signing in.

`app.py` calls `render()` before the gate. It returns True when it recognised
the requested page and drew it, and False for anything else - so an unknown or
absent `?about=` falls through to the sign-in screen rather than erroring.

WHY A QUERY PARAM and not a second `st.navigation()` tree. The gate calls
`st.stop()` before navigation is ever reached, which is what makes the app's
chrome genuinely absent rather than merely hidden (see app.py). Building a
second nav tree above that line would mean two `st.navigation()` call sites
competing to resolve the same URL, and the gate already carries CSS that hides
`stTopNavSection` to kill tabs left stale by a sign-out - so the two mechanisms
would fight. A query param needs none of that: it is read before anything is
drawn, it is shareable, and it reuses the `?account=<id>` + `target="_self"`
link pattern the account cards already prove works (gate.py).

NO CONTAINER. Nothing here may reach `get_deps()`. `chrome.header()` is
therefore not reused - it calls `active_persona()` and `_mode_chip()`, both of
which build the container - and `chrome.paint_nav_state()` is skipped for the
same reason. `chrome.breadcrumb()` IS reused: it is a pure string builder.
"""

from __future__ import annotations

import streamlit as st

from src.web_app import chrome
from src.web_app.brand import header_data_uri
from src.web_app.views import about

GROUP = "About Fintor"

# Scoped to this render. The bar is one markdown block rather than st.columns
# for the reason _accounts_band() documents: it holds no widgets, so it does
# not need Streamlit's layout, and as a single block of markup the alignment
# is ours to set rather than something to fight six wrappers over.
PUBLIC_CHROME_CSS = (
    "<style>"
    # The SAME top inset the gate uses. Both screens now lead with the same
    # bar, so they have to start at the same y or clicking between them jogs
    # the chrome - measured at 16px, which is --gate-top (4.5rem) against the
    # app default --fin-top-gap (3.5rem). Taking the gate's value rather than
    # retuning the gate: that 4.5rem was measured against the sign-in layout
    # and is not mine to move.
    "[data-testid='stMainBlockContainer']{padding-top:var(--gate-top);}"
    # Collapse the elements that paint nothing. inject() emits a <style>, this
    # block emits another, and the theme probe is a height=0 iframe - three
    # slots in a `gap:16px` flex column, which is dead air above the bar. Same
    # treatment the gate gives them, and gate-scoped there for the same reason
    # it is shell-scoped here: the signed-in pages were tuned with those gaps
    # present.
    "[data-testid='stMainBlockContainer'] "
    "[data-testid='stElementContainer']:has(> .stMarkdown style),"
    "[data-testid='stMainBlockContainer'] "
    "[data-testid='stElementContainer']:has(iframe[height='0'])"
    "{display:none !important;}"
    # The probe goes out of flow rather than hidden - a browser may skip
    # loading an iframe inside a display:none subtree, and an unloaded probe
    # means no theme at all. theme.py records this.
    "[data-testid='stLayoutWrapper']:has(> .st-key-theme-probe)"
    "{position:absolute;width:0;height:0;overflow:hidden;}"
    # No signed-in navigation here. There is none to draw - st.navigation is
    # never reached on this path - but a sign-out leaves the previous run's
    # tabs painted, and a public page wearing the app's workspace tabs implies
    # you are half way in. Same defence as GATE_CHROME_CSS.
    "[data-testid='stTopNavLinkContainer'],"
    "[data-testid='stTopNavSection']{display:none !important;}"
    "</style>"
)


def top_bar(current: str | None = None, *, signin: bool = True) -> str:
    """The lockup, the four tabs, and optionally Sign in.

    SHARED WITH THE GATE, which renders it with current=None and signin=False -
    there is no current page there, and no point offering a link to the screen
    you are already on. One bar across both screens means clicking into a
    reference page and back moves nothing: same lockup, same tabs, same place.

    It also puts the links where a menu goes. They started under the sign-in
    card, which read as a footnote to the form rather than as navigation - the
    four pages exist for someone evaluating the build, and that reader should
    not have to look past the login to find them.

    The brand and the Sign in link both point at `?`, which drops the query and
    lands back on the gate - clicking the logo to get to the front door is what
    a reader will try first, so it may as well work.
    """
    tabs = "".join(
        f'<a href="?about={key}" target="_self"'
        + (' aria-current="page" class="is-current"' if key == current else "")
        + f">{title}</a>"
        for key, (title, _fn) in about.PUBLIC_PAGES.items()
    )
    # Both lockup variants are emitted and CSS shows one. An <img> cannot
    # inherit colour, and picking server-side goes stale the moment the viewer
    # toggles - Streamlit repaints without rerunning the script. The dark copy
    # carries alt="" so a screen reader does not read the wordmark twice.
    return (
        '<header class="pub-bar">'
        '<a class="pub-brand" href="?" target="_self" '
        'aria-label="Fintor - go to sign in">'
        f'<img class="lockup-light" src="{header_data_uri()}" alt="Fintor">'
        f'<img class="lockup-dark" src="{header_data_uri(dark=True)}" alt="">'
        "</a>"
        f'<nav class="pub-tabs" aria-label="{GROUP}">{tabs}</nav>'
        + ('<a class="pub-signin" href="?" target="_self">Sign in</a>'
           if signin else "")
        + "</header>"
    )


def render(requested: object) -> bool:
    """Draw a public About page. True if one was drawn.

    `requested` is whatever `st.query_params.get()` returned - a string in a
    real run, but AppTest hands back `parse_qs` output, so a one-element list
    is normalised rather than rejected.
    """
    if isinstance(requested, (list, tuple)):
        requested = requested[0] if requested else None
    if not requested:
        return False

    page = about.PUBLIC_PAGES.get(str(requested).strip())
    if page is None:
        # Unknown page, or AI Internals, which is not public. Falls through to
        # the gate: a stale or hand-typed link should meet the front door, not
        # an error.
        return False

    title, run = page
    st.markdown(PUBLIC_CHROME_CSS, unsafe_allow_html=True)
    st.markdown(top_bar(str(requested).strip()), unsafe_allow_html=True)
    st.markdown(chrome.breadcrumb(GROUP, title), unsafe_allow_html=True)
    st.markdown('<div class="chrome-rule"></div>', unsafe_allow_html=True)
    run()
    return True
