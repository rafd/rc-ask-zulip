import pytest

from openai import OpenAI

from agent import (
    DEFAULT_OPENAI_API_KEY,
    DEFAULT_AI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    _chat_model,
    _openai_client,
)


def _api_key_plain(client: OpenAI) -> str:
    key = client.api_key
    if hasattr(key, "get_secret_value"):
        return key.get_secret_value()
    return str(key)


@pytest.fixture(autouse=True)
def clear_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(key, raising=False)


def test_openai_client_defaults() -> None:
    client = _openai_client()
    base = str(client.base_url).rstrip("/")
    assert base.endswith(DEFAULT_AI_BASE_URL.rstrip("/"))
    assert _api_key_plain(client) == DEFAULT_OPENAI_API_KEY


def test_openai_client_respects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1/")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client = _openai_client()
    assert "example.invalid" in str(client.base_url)
    assert _api_key_plain(client) == "sk-test"


def test_openai_client_strips_trailing_slash_from_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1///")
    client = _openai_client()
    base = str(client.base_url).rstrip("/")
    assert base == "http://127.0.0.1:11434/v1"


def test_chat_model_default() -> None:
    assert _chat_model() == DEFAULT_OPENAI_MODEL


def test_chat_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "qwen2.5")
    assert _chat_model() == "qwen2.5"
