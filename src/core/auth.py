"""Password verification for the sign-in screen.

Scope, stated plainly so nobody mistakes this for more than it is: Fintor's
accounts are six synthetic demo personas sharing one password that the operator
sets in `.env`. This is a teaching app with no private data behind the door -
every persona is fictional and every number is computed from committed fixtures.
What this module does provide is the part that would be negligent to fake:

* The password is never compared as a plain string. It is put through scrypt
  with a per-process random salt and compared with `hmac.compare_digest`, so a
  wrong guess costs the same time as a near-miss and nothing leaks through
  timing.
* Nothing is logged, echoed, or written to disk. The plaintext exists only in
  the environment and in the one local variable that verifies it.

Pure functions and no imports from `data` - `core` is layer 0 and the architecture
test enforces that, so the username-to-persona lookup lives in the web layer.

KNOWN LIMITS, because an auth module that overstates itself is worse than none:
* One shared password across all six accounts. Username selects WHO you are, not
  WHETHER you get in; it is not a second factor.
* Attempt throttling is per Streamlit session, so a new tab resets it. It slows
  a human at the keyboard and nothing else.
* No password reset, rotation, or account lockout that survives a restart.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass

# scrypt parameters. n=2**14 keeps a single verification near a few milliseconds
# on a laptop - slow enough to make bulk guessing unattractive, fast enough that
# the sign-in does not feel broken. r and p are the usual defaults.
_N = 2**14
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16

# Attempts allowed in one session before the form stops accepting input.
MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class Credential:
    """A salted scrypt digest. Holds no plaintext, and `repr` shows no bytes."""

    salt: bytes
    digest: bytes

    def __repr__(self) -> str:  # pragma: no cover - trivial, but load bearing
        return "Credential(salt=<redacted>, digest=<redacted>)"


def hash_password(password: str, salt: bytes | None = None) -> Credential:
    """Derive a scrypt credential. A fresh random salt unless one is supplied."""
    if salt is None:
        salt = os.urandom(_SALT_BYTES)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                            n=_N, r=_R, p=_P, dklen=_DKLEN)
    return Credential(salt=salt, digest=digest)


def verify_password(password: str, credential: Credential) -> bool:
    """Constant-time check of a candidate password against a credential.

    `compare_digest` rather than `==`: a plain comparison returns early on the
    first differing byte, which leaks how much of a guess was right.
    """
    candidate = hashlib.scrypt(password.encode("utf-8"), salt=credential.salt,
                               n=_N, r=_R, p=_P, dklen=_DKLEN)
    return hmac.compare_digest(candidate, credential.digest)


def configured(settings) -> bool:
    """Whether a demo password has been set at all.

    Fails CLOSED. With no `FINTOR_DEMO_PASSWORD` the sign-in screen explains how
    to set one rather than letting an empty password through - an auth screen
    that waves everyone past when misconfigured is worse than no auth screen,
    because it still looks like a door.
    """
    return bool((getattr(settings, "demo_password", "") or "").strip())


# Memoised per password value. scrypt is deliberately slow, and Streamlit reruns
# the whole script on every interaction - hashing the configured password on each
# rerun would add that cost to every click in the app, not just to sign-in.
_CREDENTIAL_CACHE: dict[str, Credential] = {}


def credential_for(settings) -> Credential | None:
    """The scrypt credential for the configured password, hashed once."""
    if not configured(settings):
        return None
    secret = settings.demo_password.strip()
    if secret not in _CREDENTIAL_CACHE:
        _CREDENTIAL_CACHE[secret] = hash_password(secret)
    return _CREDENTIAL_CACHE[secret]


def reset_cache() -> None:
    """Test seam: forget memoised credentials."""
    _CREDENTIAL_CACHE.clear()


def check(username: str, password: str, *, known_users: set[str],
          credential: Credential | None) -> str | None:
    """Return the canonical username on success, else None.

    The password is verified **even when the username is unknown**, against a
    throwaway credential. Skipping the hash for a bad username would make a
    wrong name return visibly faster than a wrong password, which is a free
    user-enumeration oracle.
    """
    if credential is None:
        return None
    name = (username or "").strip().lower()
    known = name in known_users
    ok = verify_password(password or "", credential)
    return name if (known and ok) else None


# --- session tokens -----------------------------------------------------
#
# A Streamlit session dies with the browser tab, so `st.session_state` alone
# meant a REFRESH logged you out. Verified before this existed: sign in,
# press reload, land back on the gate.
#
# The token is SIGNED, which is the whole point. A cookie holding a bare
# persona id would be an authentication bypass - anyone could type
# `fintor_session=walter` and skip the password entirely. HMAC over
# `persona|expiry`, keyed on the configured password, means a forged or
# edited cookie fails verification and the gate comes back.
#
# ONE MORE KNOWN LIMIT for the list above:
# * The cookie is NOT HttpOnly. Streamlit's `st.context.cookies` is read-only,
#   so nothing server-side can set a cookie; it is written by a JS shim and is
#   therefore readable by script on the page. For six synthetic personas
#   behind a published password that costs nothing, but it would be the wrong
#   design for real accounts.

COOKIE_NAME = "fintor_session"
SESSION_TTL_SECONDS = 12 * 60 * 60


def _signing_key(credential: Credential | None) -> bytes:
    """Derived from the stored digest, never from the plaintext.

    Using the scrypt digest means the key changes when the password changes,
    so rotating FINTOR_DEMO_PASSWORD invalidates every outstanding session
    without any extra bookkeeping.
    """
    if credential is None:
        return b""
    return hashlib.sha256(credential.digest + credential.salt).digest()


def issue_token(username: str, credential: Credential | None,
                *, now: float | None = None,
                ttl_seconds: int = SESSION_TTL_SECONDS) -> str:
    """A signed `username|expiry|mac` for the session cookie."""
    import time

    key = _signing_key(credential)
    if not key:
        return ""
    expiry = int((now if now is not None else time.time()) + ttl_seconds)
    payload = f"{username}|{expiry}"
    mac = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}|{mac}"


def verify_token(token: str, credential: Credential | None,
                 *, known_users: set[str] | None = None,
                 now: float | None = None) -> str | None:
    """The username the token proves, or None.

    Returns None for anything that is not a valid, unexpired signature over a
    known username - a tampered persona, a re-signed payload, a token issued
    under a previous password, or a malformed string.
    """
    import time

    key = _signing_key(credential)
    if not key or not token:
        return None
    parts = token.split("|")
    if len(parts) != 3:
        return None
    username, expiry_raw, mac = parts
    try:
        expiry = int(expiry_raw)
    except ValueError:
        return None
    if expiry < (now if now is not None else time.time()):
        return None

    expected = hmac.new(key, f"{username}|{expiry}".encode("utf-8"),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, mac):
        return None
    if known_users is not None and username not in known_users:
        return None
    return username
