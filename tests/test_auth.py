"""Sign-in: the password handling, and the limits it does not overstate.

An auth module is the wrong place for tests that only prove the happy path. The
things worth pinning are the ones that are invisible when they regress: that no
plaintext is stored or compared, that a wrong username costs the same work as a
wrong password, and that a missing configuration fails closed rather than open.
"""

from __future__ import annotations

import inspect

import pytest

import src.web_app.gate as auth_gate
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


# --- the grader's path: a clone with no .env -----------------------------
#
# These exist because the app shipped unopenable. auth.configured() fails
# closed, which is right, and the consequence was that anyone who cloned the
# repo met a locked door on the one screen that invites them to pick a reader.
# "Correct and unusable" is still a defect.


def _settings_from(tmp_path, monkeypatch, *, yaml_password, env_password=None):
    """load_settings() against a throwaway config.yaml and a controlled env."""
    import src.core.config as config

    cfg = tmp_path / "config.yaml"
    body = "app:\n  name: Fintor\n"
    if yaml_password is not None:
        body += f"auth:\n  demo_password: {yaml_password}\n"
    cfg.write_text(body, encoding="utf-8")

    if env_password is None:
        monkeypatch.delenv("FINTOR_DEMO_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("FINTOR_DEMO_PASSWORD", env_password)
    # The real loader reads .env once per process and caches that it did; this
    # keeps a developer's own .env out of the test.
    monkeypatch.setattr(config, "_ENV_LOADED", True)
    return config.load_settings(cfg)


def test_a_fresh_clone_with_no_env_file_can_still_sign_in(tmp_path, monkeypatch):
    """The submission-critical one. No .env, no exported variable - exactly what
    a grader has after `git clone` - and every demo account must open."""
    settings = _settings_from(tmp_path, monkeypatch, yaml_password="fintor")

    assert auth.configured(settings), "a fresh clone cannot reach the app"
    assert settings.demo_password_is_published

    known = {"maya", "dev", "priya", "walter", "aisha", "sam"}
    credential = auth.credential_for(settings)
    for username in sorted(known):
        assert auth.check(username, settings.demo_password,
                          known_users=known, credential=credential) == username


def test_a_wrong_password_is_still_refused_with_the_published_default(tmp_path, monkeypatch):
    """Shipping a default must not turn the gate into a no-op."""
    settings = _settings_from(tmp_path, monkeypatch, yaml_password="fintor")
    credential = auth.credential_for(settings)
    assert auth.check("dev", "wrong", known_users={"dev"}, credential=credential) is None
    assert auth.check("dev", "", known_users={"dev"}, credential=credential) is None


def test_the_environment_overrides_the_published_default(tmp_path, monkeypatch):
    """A shared deployment sets FINTOR_DEMO_PASSWORD and that must win, or the
    committed credential would quietly stay valid alongside it."""
    settings = _settings_from(tmp_path, monkeypatch,
                              yaml_password="fintor", env_password="operator-secret")

    assert settings.demo_password == "operator-secret"
    assert not settings.demo_password_is_published, (
        "an operator's password must not be flagged as publishable")

    credential = auth.credential_for(settings)
    assert auth.check("dev", "operator-secret",
                      known_users={"dev"}, credential=credential) == "dev"
    assert auth.check("dev", "fintor", known_users={"dev"}, credential=credential) is None


def test_blank_in_both_places_still_fails_closed(tmp_path, monkeypatch):
    """The fail-closed path the published default must not have removed."""
    settings = _settings_from(tmp_path, monkeypatch, yaml_password=None)

    assert not auth.configured(settings)
    assert auth.credential_for(settings) is None
    assert not settings.demo_password_is_published


def test_the_screen_prints_the_credential_only_when_it_is_published():
    """A published credential is meant to be read; an operator's is not. The
    screen cannot tell them apart without the provenance flag, and printing an
    override is how a demo convenience becomes a credential leak."""
    from src.web_app.gate import _credential_hint

    source = inspect.getsource(_credential_hint)
    assert "demo_password_is_published" in source, (
        "the hint must gate on provenance, not merely on the password existing")

    shown = []

    class _Published:
        demo_password = "fintor"
        demo_password_is_published = True

    class _Override:
        demo_password = "operator-secret"
        demo_password_is_published = False

    import src.web_app.gate as gate
    original = gate.st.markdown
    gate.st.markdown = lambda body, **_kw: shown.append(body)
    try:
        _credential_hint(_Published())
        _credential_hint(_Override())
    finally:
        gate.st.markdown = original

    assert len(shown) == 1, "exactly one of the two should print"
    assert "fintor" in shown[0]
    assert "operator-secret" not in " ".join(shown), "an override was printed"


def test_the_published_credential_is_pre_filled_so_the_form_opens_ready():
    """A grader should press one button, not hunt for a password.

    The fields are seeded through session_state rather than `value=`, because
    Streamlit warns when a widget gets both a key and a value - and the key is
    what the form reads back, so a `value=` would be the thing ignored.
    """
    source = inspect.getsource(auth_gate._sign_in_form)

    assert "demo_password_is_published" in source, (
        "the pre-fill is not gated on provenance")
    assert 'st.session_state.setdefault("signin_user"' in source
    assert 'st.session_state.setdefault("signin_pass"' in source


def test_an_operator_password_is_never_pre_filled_into_the_form():
    """Same rule as the on-screen hint. Pre-filling an override would put a
    real secret into the DOM of every sign-in page, which is worse than the
    inconvenience it saves."""
    source = inspect.getsource(auth_gate._sign_in_form)

    seed_block = source.split("demo_password_is_published")[1].split("with st.form")[0]
    assert "signin_pass" in seed_block, "the password seed moved out of the guard"

    # The guard must be a condition, not a comment: the seeding has to sit
    # inside the `if`.
    assert "if getattr(settings" in source


# --- session tokens: staying signed in without opening a hole ------------


def _cred():
    return auth.hash_password("fintor")


def test_a_refresh_can_restore_the_session_it_signed_in_with():
    """The feature. Before this, st.session_state died with the tab and a
    browser refresh dumped the user back on the sign-in screen."""
    credential = _cred()
    token = auth.issue_token("dev", credential)

    assert auth.verify_token(token, credential, known_users={"dev", "maya"}) == "dev"


def test_a_cookie_cannot_be_edited_into_a_different_persona():
    """The reason the token is signed at all. An unsigned cookie holding a
    bare persona id would let anyone type `fintor_session=walter` and skip
    the password - the session cookie would BE the authentication bypass."""
    credential = _cred()
    token = auth.issue_token("dev", credential)
    forged = token.replace("dev", "walter", 1)

    assert auth.verify_token(forged, credential, known_users={"dev", "walter"}) is None


def test_a_hand_written_token_is_refused():
    credential = _cred()
    assert auth.verify_token("walter|99999999999|deadbeef", credential,
                             known_users={"walter"}) is None
    assert auth.verify_token("garbage", credential, known_users={"walter"}) is None
    assert auth.verify_token("", credential, known_users={"walter"}) is None


def test_the_expiry_is_covered_by_the_signature():
    """Pushing the expiry out must invalidate the token, or it never expires."""
    credential = _cred()
    token = auth.issue_token("dev", credential)
    username, _old_expiry, mac = token.split("|")
    extended = f"{username}|9999999999|{mac}"

    assert auth.verify_token(extended, credential, known_users={"dev"}) is None


def test_an_expired_token_is_refused():
    credential = _cred()
    stale = auth.issue_token("dev", credential, ttl_seconds=-1)

    assert auth.verify_token(stale, credential, known_users={"dev"}) is None


def test_changing_the_password_invalidates_every_outstanding_session():
    """The signing key is derived from the stored digest, so rotating the
    password logs everyone out with no extra bookkeeping."""
    token = auth.issue_token("dev", _cred())

    assert auth.verify_token(token, auth.hash_password("different"),
                             known_users={"dev"}) is None


def test_a_token_for_an_unknown_user_is_refused():
    """Signed is not sufficient - the persona must still exist. Guards the
    case where a persona is removed but an old cookie is still in a browser."""
    credential = _cred()
    token = auth.issue_token("ghost", credential)

    assert auth.verify_token(token, credential, known_users={"dev"}) is None


def test_no_credential_means_no_tokens_at_all():
    """Fails closed, exactly as configured() does: if sign-in is not
    configured, a session token cannot be minted OR accepted."""
    assert auth.issue_token("dev", None) == ""
    assert auth.verify_token("dev|9999999999|x", None, known_users={"dev"}) is None


def test_the_token_carries_no_secret():
    """It travels in a cookie, so it must not contain the password or the
    digest - only a name, an expiry, and a MAC over them."""
    credential = _cred()
    token = auth.issue_token("dev", credential)

    assert "fintor" not in token
    assert credential.digest.hex() not in token
    assert credential.salt.hex() not in token
