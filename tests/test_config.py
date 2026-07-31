"""Offline tests for config/value resolution precedence."""
from socialdl import config


def test_resolve_precedence(monkeypatch):
    monkeypatch.delenv("SOCIALDL_X", raising=False)
    cfg = {"x": "from_cfg"}
    # explicit value wins over everything
    assert config.resolve("explicit", "SOCIALDL_X", cfg, "x", "default") == "explicit"
    # env beats config
    monkeypatch.setenv("SOCIALDL_X", "from_env")
    assert config.resolve(None, "SOCIALDL_X", cfg, "x", "default") == "from_env"
    # config beats default
    monkeypatch.delenv("SOCIALDL_X", raising=False)
    assert config.resolve(None, "SOCIALDL_X", cfg, "x", "default") == "from_cfg"
    # default when nothing set
    assert config.resolve(None, "SOCIALDL_X", {}, "x", "default") == "default"


def test_resolve_bool(monkeypatch):
    monkeypatch.delenv("SOCIALDL_FLAG", raising=False)
    assert config.resolve_bool(True, "SOCIALDL_FLAG", {}, "flag") is True
    assert config.resolve_bool(False, "SOCIALDL_FLAG", {"flag": True}, "flag") is True
    assert config.resolve_bool(False, "SOCIALDL_FLAG", {}, "flag") is False
    monkeypatch.setenv("SOCIALDL_FLAG", "yes")
    assert config.resolve_bool(False, "SOCIALDL_FLAG", {}, "flag") is True
    monkeypatch.setenv("SOCIALDL_FLAG", "0")
    assert config.resolve_bool(False, "SOCIALDL_FLAG", {}, "flag") is False
