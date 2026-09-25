import dataclasses

from faradium_bench.config import Settings
from faradium_bench.providers import anthropic_provider, openrouter_provider
from faradium_bench.proxy import ProxyManager, ensure_proxy_for, is_local_url

SETTINGS = Settings(
    anthropic_api_key="sk-ant-test",
    anthropic_auth="auto",
    openrouter_proxy_url="http://localhost:4000",
    proxy_master_key="sk-proxy",
    manage_proxy=True,
    docker_command="docker",
    permission_mode="acceptEdits",
    max_turns=10,
    results_dir="results",
)


def test_is_local_url():
    assert is_local_url("http://localhost:4000")
    assert is_local_url("http://127.0.0.1:4000")
    assert not is_local_url("https://proxy.example.com:4000")


def test_manager_classifies_local_and_remote():
    assert ProxyManager(SETTINGS).is_local()
    remote = dataclasses.replace(SETTINGS, openrouter_proxy_url="https://proxy.example.com")
    assert not ProxyManager(remote).is_local()


def test_is_up_false_when_unreachable():
    unreachable = dataclasses.replace(SETTINGS, openrouter_proxy_url="http://localhost:1")
    assert ProxyManager(unreachable).is_up(timeout=0.5) is False


def test_ensure_proxy_skips_anthropic():
    provider = anthropic_provider("claude-opus-4-8", SETTINGS)
    assert ensure_proxy_for(provider, SETTINGS) is None


def test_ensure_proxy_skips_when_management_disabled():
    provider = openrouter_provider("or-laguna", SETTINGS)
    disabled = dataclasses.replace(SETTINGS, manage_proxy=False)
    assert ensure_proxy_for(provider, disabled) is None


def test_ensure_proxy_skips_remote_proxy():
    remote = dataclasses.replace(SETTINGS, openrouter_proxy_url="https://proxy.example.com")
    provider = openrouter_provider("or-laguna", remote)
    assert ensure_proxy_for(provider, remote) is None
