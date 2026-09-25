from __future__ import annotations

import shlex
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from .config import Settings
from .providers import Provider, ProviderKind

_BENCH_DIR = Path(__file__).resolve().parent.parent
_COMPOSE_FILE = _BENCH_DIR / "docker-compose.proxy.yml"
_ENV_FILE = _BENCH_DIR / ".env"

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


class ProxyError(RuntimeError):
    pass


def is_local_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in _LOCAL_HOSTS


class ProxyManager:
    def __init__(self, settings: Settings):
        self.url = settings.openrouter_proxy_url.rstrip("/")
        self._docker_command = shlex.split(settings.docker_command or "docker")

    def is_up(self, timeout: float = 2.0) -> bool:
        try:
            with urllib.request.urlopen(
                f"{self.url}/health/liveliness", timeout=timeout
            ) as response:
                return response.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def is_local(self) -> bool:
        return is_local_url(self.url)

    def _compose_command(self, *args: str) -> list[str]:
        command = [*self._docker_command, "compose", "-f", str(_COMPOSE_FILE)]
        if _ENV_FILE.is_file():
            command += ["--env-file", str(_ENV_FILE)]
        return [*command, *args]

    def start_if_down(self, *, wait_timeout: float = 120.0) -> bool:
        if self.is_up():
            return False
        if not _COMPOSE_FILE.is_file():
            raise ProxyError(f"compose file not found: {_COMPOSE_FILE}")

        docker_name = " ".join(self._docker_command)

        try:
            subprocess.run(
                self._compose_command("up", "-d"),
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ProxyError(
                f"could not run '{docker_name}' — is Docker installed and on PATH? "
                "Set BENCH_DOCKER_CMD (e.g. 'sudo docker') if it needs different invocation."
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            hint = ""
            if "permission denied" in detail.lower():
                hint = " (docker needs elevated permissions — try BENCH_DOCKER_CMD='sudo docker')"
            raise ProxyError(f"docker compose up failed{hint}:\n{detail}") from exc

        deadline = time.monotonic() + wait_timeout
        while time.monotonic() < deadline:
            if self.is_up():
                return True
            time.sleep(2.0)

        raise ProxyError(
            f"proxy started but did not become reachable at {self.url} within "
            f"{wait_timeout:.0f}s — check `{docker_name} compose "
            f"-f {_COMPOSE_FILE} logs`."
        )

    def down(self) -> None:
        try:
            subprocess.run(
                self._compose_command("down"), check=True, capture_output=True, text=True
            )
        except FileNotFoundError as exc:
            raise ProxyError(
                f"could not run '{' '.join(self._docker_command)}' to stop the proxy."
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            raise ProxyError(f"docker compose down failed:\n{detail}") from exc


def ensure_proxy_for(provider: Provider, settings: Settings) -> ProxyManager | None:
    if provider.kind is not ProviderKind.OPENROUTER:
        return None
    if not settings.manage_proxy:
        return None

    manager = ProxyManager(settings)
    if not manager.is_local():
        return None

    started = manager.start_if_down()
    if started:
        print(f"[proxy] started LiteLLM proxy at {manager.url}")
    else:
        print(f"[proxy] reusing LiteLLM proxy already running at {manager.url}")

    return manager
