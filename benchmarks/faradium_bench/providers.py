from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum

from .config import Settings


class ProviderKind(StrEnum):
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"


class AuthMode(StrEnum):
    API_KEY = "api-key"
    SUBSCRIPTION = "subscription"
    PROXY = "proxy"


_AUTH_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
_ROUTING_VARS = (*_AUTH_VARS, "ANTHROPIC_BASE_URL")


@dataclass(frozen=True)
class Provider:
    name: str
    kind: ProviderKind
    model: str
    auth_mode: AuthMode = AuthMode.API_KEY
    auth_token: str = ""
    base_url: str | None = None

    def routing_env(self) -> dict[str, str]:
        if self.auth_mode is AuthMode.SUBSCRIPTION:
            return {}
        if self.kind is ProviderKind.ANTHROPIC:
            return {"ANTHROPIC_API_KEY": self.auth_token}

        routing_env = {"ANTHROPIC_AUTH_TOKEN": self.auth_token}
        if self.base_url:
            routing_env["ANTHROPIC_BASE_URL"] = self.base_url
        return routing_env


def _resolve_anthropic_auth(settings: Settings, requested: str | None) -> AuthMode:
    choice = (requested or settings.anthropic_auth or "auto").strip().lower()
    if choice in ("api-key", "api_key", "key"):
        return AuthMode.API_KEY
    if choice in ("subscription", "sub", "login"):
        return AuthMode.SUBSCRIPTION

    return AuthMode.API_KEY if settings.anthropic_api_key else AuthMode.SUBSCRIPTION


def anthropic_provider(
    model: str, settings: Settings, *, name: str | None = None, auth: str | None = None
) -> Provider:
    auth_mode = _resolve_anthropic_auth(settings, auth)
    if auth_mode is AuthMode.API_KEY and not settings.anthropic_api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY is not set — needed for api-key auth. "
            "Omit it (and log in with `claude`) to use your subscription instead."
        )

    return Provider(
        name=name or f"anthropic/{model}",
        kind=ProviderKind.ANTHROPIC,
        model=model,
        auth_mode=auth_mode,
        auth_token=settings.anthropic_api_key if auth_mode is AuthMode.API_KEY else "",
    )


def openrouter_provider(model: str, settings: Settings, *, name: str | None = None) -> Provider:
    if not settings.proxy_master_key:
        raise ValueError(
            "LITELLM_MASTER_KEY is not set — needed to authenticate to the OpenRouter proxy"
        )

    return Provider(
        name=name or f"openrouter/{model}",
        kind=ProviderKind.OPENROUTER,
        model=model,
        auth_mode=AuthMode.PROXY,
        auth_token=settings.proxy_master_key,
        base_url=settings.openrouter_proxy_url,
    )


@contextlib.contextmanager
def apply_env(provider: Provider) -> Iterator[None]:
    snapshot = {name: os.environ.get(name) for name in _ROUTING_VARS}

    try:
        for name in _ROUTING_VARS:
            os.environ.pop(name, None)
        os.environ.update(provider.routing_env())

        yield
    finally:
        for name, value in snapshot.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
