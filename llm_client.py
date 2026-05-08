"""Shared OpenAI-compatible client construction with a hard guard against
known commercial LLM providers (OpenAI / ChatGPT, Anthropic / Claude, and
Google Gemini).

Other endpoints — local Ollama, self-hosted gateways, third-party proxies,
LAN-hosted models, etc. — are allowed. This guard exists specifically to
prevent accidental data leakage to the three big proprietary services if a
user has a real OPENAI_API_KEY in their .env and someone (re)points
OPENAI_BASE_URL at one of them.

To extend the denylist, append a hostname suffix to BLOCKED_PROVIDER_SUFFIXES.
"""
import os
from urllib.parse import urlparse

from openai import OpenAI

LOCAL_OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
LOCAL_OLLAMA_API_KEY = "ollama"

# Hostname suffixes for providers we refuse to call. Matched as a full host
# match OR a `.suffix` match (so "api.openai.com" matches "openai.com" but
# "myopenai.com" does not).
BLOCKED_PROVIDER_SUFFIXES: tuple[str, ...] = (
    "openai.com",          # ChatGPT / OpenAI API
    "anthropic.com",       # Claude API
    "claude.ai",           # Claude web
    "googleapis.com",      # Gemini / Vertex AI live under *.googleapis.com
)


class ExternalLLMNotAllowedError(RuntimeError):
    """Raised when OPENAI_BASE_URL points at a blocked commercial LLM
    provider (OpenAI/ChatGPT, Anthropic/Claude, Google Gemini)."""


def _hostname_matches_suffix(host: str, suffix: str) -> bool:
    host = host.lower()
    suffix = suffix.lower()
    return host == suffix or host.endswith("." + suffix)


def assert_not_blocked_provider(url: str) -> None:
    """Raise ExternalLLMNotAllowedError if `url` points at a blocked provider.

    Allowed: anything *not* on BLOCKED_PROVIDER_SUFFIXES — local Ollama,
    self-hosted gateways, third-party proxies, etc.

    Rejected: api.openai.com, api.anthropic.com, claude.ai,
    generativelanguage.googleapis.com, aiplatform.googleapis.com, etc.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ExternalLLMNotAllowedError(
            f"Could not parse hostname from OPENAI_BASE_URL={url!r}"
        )
    for suffix in BLOCKED_PROVIDER_SUFFIXES:
        if _hostname_matches_suffix(host, suffix):
            raise ExternalLLMNotAllowedError(
                f"OPENAI_BASE_URL points at blocked provider host {host!r} "
                f"(matches '{suffix}'). This project does not call ChatGPT, "
                f"Claude, or Gemini directly. Use a local Ollama instance "
                f"({LOCAL_OLLAMA_BASE_URL}) or a non-blocked OpenAI-compatible "
                f"endpoint instead."
            )


def configured_base_url() -> str:
    """Return the base URL that build_openai_client() will use, after
    applying the local Ollama default. Useful for startup checks."""
    return os.environ.get("OPENAI_BASE_URL", LOCAL_OLLAMA_BASE_URL).rstrip("/")


def build_openai_client(timeout: float | None = None) -> OpenAI:
    """Construct an OpenAI-compatible client.

    Raises ExternalLLMNotAllowedError if OPENAI_BASE_URL is set to a known
    blocked provider (OpenAI, Anthropic, Google Gemini). This is the single
    allowed factory for OpenAI clients in this project.
    """
    base_url = configured_base_url()
    assert_not_blocked_provider(base_url)
    api_key = os.environ.get("OPENAI_API_KEY", LOCAL_OLLAMA_API_KEY)
    if timeout is None:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
