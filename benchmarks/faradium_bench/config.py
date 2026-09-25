from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_PACKAGE_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_env_files() -> None:
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return

    explicit_env_file = os.environ.get("BENCH_ENV_FILE", "").strip()
    if explicit_env_file:
        load_dotenv(explicit_env_file, override=False)
        return

    loaded_paths: set[str] = set()
    cwd_env_file = find_dotenv(usecwd=True)
    if cwd_env_file:
        load_dotenv(cwd_env_file, override=False)
        loaded_paths.add(str(Path(cwd_env_file).resolve()))

    if _PACKAGE_ENV_FILE.is_file() and str(_PACKAGE_ENV_FILE) not in loaded_paths:
        load_dotenv(_PACKAGE_ENV_FILE, override=False)


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    anthropic_auth: str

    openrouter_proxy_url: str
    proxy_master_key: str

    manage_proxy: bool
    docker_command: str

    permission_mode: str
    max_turns: int
    results_dir: str

    @classmethod
    def load(cls) -> Settings:
        load_env_files()

        return cls(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
            anthropic_auth=os.environ.get("BENCH_ANTHROPIC_AUTH", "auto").strip().lower(),
            openrouter_proxy_url=os.environ.get(
                "OPENROUTER_PROXY_URL", "http://localhost:4000"
            ).strip(),
            proxy_master_key=os.environ.get("LITELLM_MASTER_KEY", "").strip(),
            manage_proxy=_env_bool("BENCH_MANAGE_PROXY", default=True),
            docker_command=os.environ.get("BENCH_DOCKER_CMD", "docker").strip(),
            permission_mode=os.environ.get("BENCH_PERMISSION_MODE", "bypassPermissions").strip(),
            max_turns=int(os.environ.get("BENCH_MAX_TURNS", "40")),
            results_dir=os.environ.get("BENCH_RESULTS_DIR", "results").strip(),
        )
