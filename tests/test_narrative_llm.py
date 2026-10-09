from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

from invest_system.narrative import llm


def test_number_check_handles_vietnamese_format_without_collisions():
    assert llm._numbers("GDP 6,5%; vốn hóa 1.234,50 tỷ") == llm._numbers(
        "GDP 6.50%; vốn hóa 1.234,5 tỷ"
    )
    assert llm._numbers("Tăng 6,5%") != llm._numbers("Tăng 65%")


def test_polish_uses_responses_api_and_keeps_figures(monkeypatch):
    captured = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text="GDP đạt 6,5%, hỗ trợ sức cầu.")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.responses = FakeResponses()

    fake_module = ModuleType("openai")
    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_ENABLED", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    result = llm.polish("Vĩ mô", ["GDP đạt 6,5%, hỗ trợ sức cầu."])

    assert result == ["GDP đạt 6,5%, hỗ trợ sức cầu."]
    assert captured["model"] == "test-model"
    assert captured["client"]["api_key"] == "test-key"
    assert "instructions" in captured


def test_polish_rejects_added_or_changed_numbers(monkeypatch):
    class FakeResponses:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="GDP đạt 65%, hỗ trợ sức cầu.")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = FakeResponses()

    fake_module = ModuleType("openai")
    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_ENABLED", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    original = ["GDP đạt 6,5%, hỗ trợ sức cầu."]
    assert llm.polish("Vĩ mô", original) == original


def test_polish_falls_back_when_not_configured(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_ENABLED", "1")
    original = ["Nhận định có sẵn."]
    assert llm.polish("Vĩ mô", original) is original


def test_macro_analysis_receives_source_data_and_computed_scores(monkeypatch):
    captured = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text="GDP đạt 6,5%; bối cảnh hỗ trợ ngành.")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = FakeResponses()

    fake_module = ModuleType("openai")
    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_ENABLED", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    macro = SimpleNamespace(
        commentary=["GDP đạt 6,5%."],
        table=[{"key": "gdp_growth", "value": 6.5, "period": "2026-Q2", "source": "GSO"}],
        score=58.0,
        sector_label="Bất động sản",
        sector_score=54.0,
        notes=[],
    )

    result = llm.analyze_macro({"macro": macro})

    assert result == ["GDP đạt 6,5%; bối cảnh hỗ trợ ngành."]
    assert "GSO" in captured["input"]
    assert "58.0" in captured["input"]
    assert "kênh truyền dẫn" in captured["instructions"]


def test_macro_analysis_rejects_numbers_missing_from_source(monkeypatch):
    class FakeResponses:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="GDP đạt 6,5%; CPI là 3,2%.")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = FakeResponses()

    fake_module = ModuleType("openai")
    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_ENABLED", "1")
    macro = SimpleNamespace(
        commentary=["GDP đạt 6,5%."], table=[], score=58.0,
        sector_label="Ngành", sector_score=54.0, notes=[],
    )

    assert llm.analyze_macro({"macro": macro}) == ["GDP đạt 6,5%."]


def test_gemini_provider_can_polish_without_calling_openai(monkeypatch):
    captured = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="Nhận định chuyên nghiệp.")

    fake_genai = SimpleNamespace(Client=lambda api_key: SimpleNamespace(models=FakeModels()))
    fake_google = ModuleType("google")
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key-must-not-be-used")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("LLM_ENABLED", "1")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")

    result = llm.polish("Doanh nghiệp", ["Nhận định cơ sở."])

    assert result == ["Nhận định chuyên nghiệp."]
    assert captured["model"] == "gemini-test-model"
    assert captured["contents"]
    assert captured["config"]["max_output_tokens"] == 500


def test_keys_alone_do_not_enable_llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_ENABLED", "0")
    assert not llm.enabled()


def test_selected_provider_requires_its_own_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_ENABLED", "1")
    assert not llm.enabled()
