from __future__ import annotations

import contextlib
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path


def _git(workdir: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=workdir, check=True)


def git_diff(workdir: Path) -> str:
    result = subprocess.run(["git", "diff", "HEAD"], cwd=workdir, capture_output=True, text=True)
    return result.stdout or ""


def init_repo(workdir: Path) -> None:
    _git(workdir, "init", "-q")
    _git(workdir, "add", "-A")
    _git(workdir, "-c", "user.email=b@b", "-c", "user.name=bench", "commit", "-q", "-m", "base")


def reset_repo(workdir: Path) -> None:
    _git(workdir, "reset", "--hard", "-q", "HEAD")
    _git(workdir, "clean", "-fdq")


def copy_repo(base: Path, dest: Path) -> Path:
    shutil.copytree(base, dest)
    return dest


def append_text(path: Path, text: str) -> None:
    path.write_text(path.read_text() + text)


@contextlib.contextmanager
def temporary_test_file(workdir: Path, name: str, code: str) -> Iterator[Path]:
    test_file = workdir / "tests" / name
    test_file.write_text(code)

    try:
        yield test_file
    finally:
        if test_file.exists():
            test_file.unlink()


def run_pytest(
    workdir: Path, target: str, timeout: int, *, collect_only: bool = False
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "pytest"]
    if collect_only:
        command.append("--collect-only")

    return subprocess.run(
        [*command, "-q", target],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def captured_output(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stdout or "") + (result.stderr or "")


def tail_lines(text: str, count: int) -> str:
    return "\n".join(text.strip().splitlines()[-count:])
