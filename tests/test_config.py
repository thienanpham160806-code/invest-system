import pytest

from invest_system.config import Settings


def _settings() -> Settings:
    return Settings(
        {"universe": {"max_symbols": 0}, "market_store": {"count_back_bootstrap": 500}}
    )


def test_env_overrides_yaml_value(monkeypatch):
    monkeypatch.setenv("UNIVERSE_MAX_SYMBOLS", "300")
    monkeypatch.setenv("MARKET_COUNT_BACK", "400")
    settings = _settings()
    assert settings.get("universe.max_symbols") == 300
    assert settings.get("market_store.count_back_bootstrap") == 400


def test_yaml_value_used_when_env_unset_or_blank(monkeypatch):
    monkeypatch.delenv("UNIVERSE_MAX_SYMBOLS", raising=False)
    monkeypatch.setenv("MARKET_COUNT_BACK", "  ")
    settings = _settings()
    assert settings.get("universe.max_symbols") == 0
    assert settings.get("market_store.count_back_bootstrap") == 500


def test_invalid_env_value_raises_clear_error(monkeypatch):
    monkeypatch.setenv("UNIVERSE_MAX_SYMBOLS", "abc")
    with pytest.raises(ValueError, match="UNIVERSE_MAX_SYMBOLS"):
        _settings().get("universe.max_symbols")
