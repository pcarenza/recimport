import pytest

from auth import EnvTokenStore, User, parse_bearer

T1 = "a" * 16
T2 = "b" * 20
T3 = "c" * 16


def test_single_token():
    s = EnvTokenStore({"APP_TOKEN": T1})
    assert s.configured
    assert s.resolve(T1) == User("owner")


def test_multiple_tokens_with_whitespace():
    s = EnvTokenStore({"APP_TOKENS": f" alice : {T1} , bob:{T2} "})
    assert s.resolve(T1) == User("alice")
    assert s.resolve(T2) == User("bob")


def test_both_together():
    s = EnvTokenStore({"APP_TOKEN": T1, "APP_TOKENS": f"bob:{T2}"})
    assert s.resolve(T1) == User("owner")
    assert s.resolve(T2) == User("bob")


def test_malformed_items_skipped():
    s = EnvTokenStore({"APP_TOKENS": f"nocolon,,:{T1},carl:,dave:{T3}"})
    assert s.configured
    assert s.resolve(T3) == User("dave")
    assert s.resolve(T1) is None


def test_colon_in_token_preserved():
    tok = "abc:def:ghi:jklmnop"
    s = EnvTokenStore({"APP_TOKENS": f"eve:{tok}"})
    assert s.resolve(tok) == User("eve")
    assert s.resolve("def:ghi:jklmnop") is None


def test_short_token_raises_without_echo():
    short = "sekret123"
    with pytest.raises(ValueError) as e:
        EnvTokenStore({"APP_TOKEN": short})
    assert short not in str(e.value)
    with pytest.raises(ValueError) as e:
        EnvTokenStore({"APP_TOKENS": f"x:{short}"})
    assert short not in str(e.value)


def test_unconfigured():
    s = EnvTokenStore({})
    assert not s.configured
    assert s.resolve(T1) is None


def test_defaults_to_os_environ(monkeypatch):
    monkeypatch.setenv("APP_TOKEN", T1)
    monkeypatch.delenv("APP_TOKENS", raising=False)
    assert EnvTokenStore().resolve(T1) == User("owner")


def test_wrong_empty_none():
    s = EnvTokenStore({"APP_TOKEN": T1})
    assert s.resolve("wrong" * 5) is None
    assert s.resolve("") is None
    assert s.resolve(None) is None


@pytest.mark.parametrize(
    "header,expected",
    [
        ("Bearer abc", "abc"),
        ("bearer abc", "abc"),
        ("BEARER abc", "abc"),
        (None, None),
        ("", None),
        ("Bearer", None),
        ("Bearer ", None),
        ("Basic abc", None),
        ("Bearerabc", None),
    ],
)
def test_parse_bearer(header, expected):
    assert parse_bearer(header) == expected
