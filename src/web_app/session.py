"""Keeping a signed-in user signed in across a browser refresh.

A Streamlit session ends with the tab, so `st.session_state["persona_id"]`
alone meant reload = logged out. Measured before this existed: sign in, press
F5, land back on the gate.

`st.context.cookies` is READ-ONLY - Streamlit can see the cookies the browser
sent with the initial request but cannot set one. So the cookie is written by
a tiny JS shim, the same `components.v1.html` trick the theme probe already
uses, and read back server-side on the next load.

The token is signed (see `src/core/auth.py`). A cookie carrying a bare persona
id would let anyone skip the password by typing `fintor_session=walter`.
"""

from __future__ import annotations

import streamlit as st

from src.core import auth
from src.web_app.state import app_settings

_RESTORED = "_session_restored"


def _emit(script: str) -> None:
    """Run a line of JS against the PARENT document.

    height=0 and out of flow: this paints nothing, and a visible iframe would
    take a 16px flex gap from Streamlit's vertical block - the same way the
    theme probe did before it was positioned absolutely.
    """
    import streamlit.components.v1 as components

    with st.container(key="session-cookie"):
        components.html(f"<script>{script}</script>", height=0)


_WRITTEN = "_session_cookie_for"


def sync(username: str) -> None:
    """Make sure the browser holds a current cookie for this user.

    Called on every signed-in run but emits only when the stored value is
    stale, so a normal rerun costs nothing. It cannot be done at the moment of
    sign-in: `st.rerun()` throws away the current render, component included.
    """
    if st.session_state.get(_WRITTEN) == username:
        return
    st.session_state[_WRITTEN] = username
    _remember(username)


def _remember(username: str) -> None:
    """Write the signed session cookie."""
    settings = app_settings()
    token = auth.issue_token(username, auth.credential_for(settings))
    if not token:
        return
    _emit(
        f"const d=window.parent.document;"
        f"d.cookie={auth.COOKIE_NAME!r}+'='+{token!r}"
        f"+';path=/;max-age={auth.SESSION_TTL_SECONDS};samesite=Lax';"
    )


_PENDING_CLEAR = "_session_clear_pending"


def forget() -> None:
    """Mark the cookie for clearing on the next run.

    It cannot be cleared here. Sign-out ends with `st.rerun()`, which throws
    away everything the current run produced - the component included - so JS
    emitted on this line never reaches the browser. That bug survived the
    first fix: sign-out LOOKED right because the gate came back, and only a
    refresh afterwards revealed the cookie was still there and signed the
    user straight back in.
    """
    st.session_state.pop(_WRITTEN, None)
    st.session_state[_PENDING_CLEAR] = True


def apply_pending() -> None:
    """Emit any deferred cookie clear. Called early, before the gate."""
    if not st.session_state.pop(_PENDING_CLEAR, False):
        return
    _emit(
        f"const d=window.parent.document;"
        f"d.cookie={auth.COOKIE_NAME!r}+'=;path=/;max-age=0;samesite=Lax';"
    )


def restore(known_users: set[str]) -> str | None:
    """Put the persona back into session_state from a valid cookie.

    Runs once per Streamlit session - the `_RESTORED` flag stops a signed-out
    user being signed straight back in by a cookie the browser is still
    sending, which would make the Sign out button appear broken until the
    cookie expired.
    """
    if st.session_state.get(_RESTORED):
        return None
    st.session_state[_RESTORED] = True

    try:
        token = st.context.cookies.get(auth.COOKIE_NAME)
    except Exception:  # noqa: BLE001 - no context in tests or bare mode
        return None
    if not token:
        return None

    settings = app_settings()
    username = auth.verify_token(token, auth.credential_for(settings),
                                 known_users=known_users)
    if username:
        st.session_state["persona_id"] = username
    return username
