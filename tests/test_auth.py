"""Sign-in: the password handling, and the limits it does not overstate.

An auth module is the wrong place for tests that only prove the happy path. The
things worth pinning are the ones that are invisible when they regress: that no
plaintext is stored or compared, that a wrong username costs the same work as a
wrong password, and that a missing configuration fails closed rather than open.
"""

from __future__ import annotations

import inspect

import pytest

from src.core import auth


@pytest.fixture(autouse=True)
def _clear_cache():
    auth.reset_cache()
    yield
    auth.reset_cache()


class _Settings:
    """Stand-in; the real Settings is frozen and reads the environment."""

    def __init__(self, demo_password: str = "") -> None:
        self.demo_password = demo_password


# --- hashing ------------------------------------------------------------


def test_a_password_round_trips():
    credential = auth.hash_password("correct horse battery staple")
    assert auth.verify_password("correct horse battery staple", credential)
    assert not auth.verify_password("correct horse battery stapl", credential)


def test_the_same_password_hashes_differently_each_time():
    """A fresh random salt per credential, so two users with the same password
    do not share a digest and a precomputed table buys nothing."""
    a = auth.hash_password("same")
    b = auth.hash_password("same")
    assert a.salt != b.salt
    assert a.digest != b.digest
    assert auth.verify_password("same", a) and auth.verify_password("same", b)


def test_the_credential_never_carries_the_plaintext():
    credential = auth.hash_password("hunter2")
    assert b"hunter2" not in credential.digest
    assert b"hunter2" not in credential.salt


def test_the_credential_repr_shows_nothing():
    """It ends up in tracebacks and debugger frames."""
    credential = auth.hash_password("hunter2")
    assert "hunter2" not in repr(credential)
    assert "redacted" in repr(credential)


def test_the_settings_repr_hides_the_demo_password():
    from src.core.config import Settings

    settings = Settings(raw={}, demo_password="hunter2")
    assert "hunter2" not in repr(settings)


# --- comparison ---------------------------------------------------------


def test_verification_uses_a_constant_time_compare():
    """`==` on digests returns early at the first differing byte, which leaks
    how much of a guess was right. This is not observable from the outside, so
    it is pinned at the source."""
    src = inspect.getsource(auth.verify_password)
    assert "compare_digest" in src
    assert "==" not in src.split('"""')[-1], "a plain comparison crept back in"


def test_an_unknown_username_still_pays_for_the_hash():
    """Returning early on an unknown username makes a bad name measurably
    faster than a bad password, which is a free user-enumeration oracle."""
    src = inspect.getsource(auth.check)
    verify_at = src.index("verify_password")
    return_at = src.index("return name if")
    assert verify_at < return_at, "the hash must run before the decision"
    assert "if known" not in src, "an early return on an unknown user is an oracle"


def test_scrypt_is_not_tuned_down_to_nothing():
    """The cost parameter is the whole point of using a KDF."""
    assert auth._N >= 2**14
    assert auth._DKLEN >= 32


# --- the decision -------------------------------------------------------


def test_a_good_username_and_password_returns_the_username():
    credential = auth.hash_password("pw")
    assert auth.check("dev", "pw", known_users={"dev"}, credential=credential) == "dev"


def test_a_username_is_matched_case_and_space_insensitively():
    credential = auth.hash_password("pw")
    assert auth.check("  Dev ", "pw", known_users={"dev"},
                      credential=credential) == "dev"


@pytest.mark.parametrize("user,password", [
    ("dev", "wrong"),
    ("nobody", "pw"),
    ("", "pw"),
    ("dev", ""),
])
def test_anything_short_of_both_halves_fails(user, password):
    credential = auth.hash_password("pw")
    assert auth.check(user, password, known_users={"dev"},
                      credential=credential) is None


# --- failing closed -----------------------------------------------------


def test_no_configured_password_means_nobody_gets_in():
    """The dangerous regression: an unconfigured deployment that still looks
    like it has a door. A blank password must not open it."""
    settings = _Settings("")
    assert auth.configured(settings) is False
    assert auth.credential_for(settings) is None
    assert auth.check("dev", "", known_users={"dev"}, credential=None) is None
    assert auth.check("dev", "anything", known_users={"dev"}, credential=None) is None


def test_whitespace_is_not_a_password():
    assert auth.configured(_Settings("   ")) is False


def test_the_credential_is_hashed_once_not_per_rerun():
    """Streamlit reruns the whole script on every interaction. scrypt is
    deliberately slow, so hashing per rerun would put that cost on every click
    in the app rather than on sign-in."""
    settings = _Settings("pw")
    first = auth.credential_for(settings)
    assert auth.credential_for(settings) is first


# --- the gate's use of it -----------------------------------------------


def test_the_gate_fails_closed_and_says_so():
    src = inspect.getsource(__import__("src.web_app.gate", fromlist=["x"]))
    assert "auth.configured(settings)" in src, "the gate never checks configuration"
    assert "FINTOR_DEMO_PASSWORD" in src, "it should say how to configure it"


def test_the_gate_does_not_reveal_which_half_was_wrong():
    """Separate 'no such user' and 'wrong password' messages enumerate accounts."""
    src = inspect.getsource(__import__("src.web_app.gate", fromlist=["x"]))
    lowered = src.lower()
    for leak in ("unknown user", "no such user", "user not found", "wrong password",
                 "incorrect password"):
        assert leak not in lowered, f"the error message leaks: {leak!r}"


def test_the_gate_never_echoes_the_password():
    """It must not reach a log, a caption, or an error string."""
    src = inspect.getsource(__import__("src.web_app.gate", fromlist=["x"]))
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "password" not in stripped:
            continue
        if any(call in stripped for call in ("st.write", "st.caption", "st.code",
                                             "logger.", "print(")):
            raise AssertionError(f"password may be echoed: {stripped}")


def test_sign_in_is_rate_limited_within_a_session():
    src = inspect.getsource(__import__("src.web_app.gate", fromlist=["x"]))
    assert "MAX_ATTEMPTS" in src, "failed attempts are unbounded"


def test_the_limits_are_documented_rather_than_implied():
    """The throttle resets with the session and the password is shared. Both
    are fine for a teaching demo and both would be dishonest left unsaid."""
    doc = auth.__doc__ or ""
    assert "KNOWN LIMITS" in doc
    assert "shared password" in doc.lower()
    assert "session" in doc.lower()
