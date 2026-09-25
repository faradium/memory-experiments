import dataclasses
import os

import pytest

from faradium_bench.config import Settings
from faradium_bench.providers import (
    AuthMode,
    ProviderKind,
    anthropic_provider,
    apply_env,
    openrouter_provider,
)

SETTINGS = Settings(
    anthropic_api_key="sk-ant-test",
    anthropic_auth="auto",
    openrouter_proxy_url="http://proxy:4000",
    proxy_master_key="sk-proxy",
    manage_proxy=True,
    docker_command="docker",
    permission_mode="acceptEdits",
    max_turns=10,
    results_dir="results",
)


def test_anthropic_provider_uses_api_key_no_base_url():
    provider = anthropic_provider("claude-opus-4-8", SETTINGS)

    assert provider.kind is ProviderKind.ANTHROPIC
    assert provider.auth_mode is AuthMode.API_KEY
    assert provider.base_url is None
    assert provider.routing_env() == {"ANTHROPIC_API_KEY": "sk-ant-test"}


def test_anthropic_subscription_when_no_key():
    settings = dataclasses.replace(SETTINGS, anthropic_api_key="")
    provider = anthropic_provider("claude-opus-4-8", settings)

    assert provider.auth_mode is AuthMode.SUBSCRIPTION
    assert provider.auth_token == ""
    assert provider.routing_env() == {}


def test_anthropic_explicit_subscription_ignores_key():
    provider = anthropic_provider("claude-opus-4-8", SETTINGS, auth="subscription")
    assert provider.auth_mode is AuthMode.SUBSCRIPTION
    assert provider.routing_env() == {}


def test_anthropic_api_key_mode_requires_key():
    settings = dataclasses.replace(SETTINGS, anthropic_api_key="")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY is not set"):
        anthropic_provider("claude-opus-4-8", settings, auth="api-key")


def test_apply_env_subscription_clears_all_auth(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stale")

    settings = dataclasses.replace(SETTINGS, anthropic_api_key="")
    provider = anthropic_provider("claude-opus-4-8", settings, auth="subscription")
    with apply_env(provider):
        assert "ANTHROPIC_API_KEY" not in os.environ
        assert "ANTHROPIC_AUTH_TOKEN" not in os.environ
        assert "ANTHROPIC_BASE_URL" not in os.environ

    assert os.environ["ANTHROPIC_API_KEY"] == "stale"


def test_openrouter_provider_uses_bearer_and_base_url():
    provider = openrouter_provider("or-laguna", SETTINGS)

    assert provider.kind is ProviderKind.OPENROUTER
    assert provider.base_url == "http://proxy:4000"
    assert provider.routing_env() == {
        "ANTHROPIC_AUTH_TOKEN": "sk-proxy",
        "ANTHROPIC_BASE_URL": "http://proxy:4000",
    }


def test_apply_env_sets_then_restores_and_clears_other_auth_var(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stale")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    provider = openrouter_provider("or-laguna", SETTINGS)
    with apply_env(provider):
        assert os.environ["ANTHROPIC_BASE_URL"] == "http://proxy:4000"
        assert os.environ["ANTHROPIC_AUTH_TOKEN"] == "sk-proxy"
        assert "ANTHROPIC_API_KEY" not in os.environ

    assert os.environ["ANTHROPIC_API_KEY"] == "stale"
    assert "ANTHROPIC_BASE_URL" not in os.environ
    assert "ANTHROPIC_AUTH_TOKEN" not in os.environ
