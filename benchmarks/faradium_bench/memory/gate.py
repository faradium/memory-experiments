from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from ..config import Settings
from ..providers import Provider, apply_env
from ..repo import captured_output, git_diff, run_pytest, tail_lines, temporary_test_file
from . import autogate, usage

_CONVENTIONS_FEEDBACK = (
    "Mandatory project conventions — carried in memory from prior sessions on THIS repo — "
    "are VIOLATED by your change:"
    "\n\n"
    "{failures}"
    "\n\n"
    "Fix your implementation so every convention above is satisfied. "
    "Do not edit any test files. Confirm when fixed."
)


def _agent_options(
    provider: Provider, settings: Settings, workdir: Path, system_prompt, tools: list[str]
) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=provider.model,
        cwd=str(workdir),
        system_prompt=system_prompt,
        allowed_tools=tools,
        permission_mode=settings.permission_mode,
        max_turns=settings.max_turns,
    )


async def _receive_turns(client, model: str = "") -> int:
    turns = 0
    async for message in client.receive_response():
        if type(message).__name__ == "ResultMessage":
            turns = getattr(message, "num_turns", 0) or turns
            usage.add(model, getattr(message, "usage", None))

    return turns


def _failed_test_checks(workdir: Path, test_checks: list) -> list[str]:
    failures: list[str] = []
    for index, check in enumerate(test_checks):
        passed, output = run_check(workdir, check.test_code, test_file_name=f"_gate{index}.py")
        if not passed:
            tail = tail_lines(output, 12)
            failures.append(f"- CONVENTION: {check.fact}\n  CHECK FAILED:\n{tail}")

    return failures


async def _violated_judge_checks(
    judge_provider: Provider,
    judge_checks: list,
    prompt: str,
    workdir: Path,
    judge_model: str | None,
) -> list[str]:
    verdicts = await autogate.judge_diff(
        judge_provider,
        [check.fact for check in judge_checks],
        prompt,
        git_diff(workdir),
        workdir=workdir,
        model=judge_model,
    )

    return [
        f"- CONVENTION: {check.fact}\n  WHY VIOLATED: {verdict['evidence']}"
        for check, verdict in zip(judge_checks, verdicts, strict=False)
        if verdict["verdict"] == "violated"
    ]


def run_check(workdir: Path, check_code: str, test_file_name: str = "_gate.py") -> tuple[bool, str]:
    with temporary_test_file(workdir, test_file_name, check_code):
        result = run_pytest(workdir, f"tests/{test_file_name}", timeout=120)
        return result.returncode == 0, captured_output(result)


async def run_gated_session(
    provider: Provider,
    settings: Settings,
    workdir: Path,
    system_prompt,
    prompt: str,
    tools: list[str],
    checks: list,
    judge_provider: Provider | None = None,
    judge_model: str | None = None,
    max_cycles: int = 2,
    judge_all: bool = True,
) -> tuple[int, int]:
    test_checks = [check for check in checks if check.kind == "test"]
    judge_checks = checks if judge_all else [check for check in checks if check.kind == "judge"]
    options = _agent_options(provider, settings, workdir, system_prompt, tools)
    turns = 0
    cycles = 0

    with apply_env(provider):
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            turns = await _receive_turns(client, provider.model)

            for _ in range(max_cycles):
                failures = _failed_test_checks(workdir, test_checks)
                if judge_checks and (judge_provider or judge_model):
                    failures += await _violated_judge_checks(
                        judge_provider or provider, judge_checks, prompt, workdir, judge_model
                    )
                if not failures:
                    break

                cycles += 1
                await client.query(_CONVENTIONS_FEEDBACK.format(failures="\n".join(failures)))
                turns += await _receive_turns(client, provider.model)

    return turns, cycles


async def run_push_session(
    provider: Provider,
    settings: Settings,
    workdir: Path,
    system_prompt,
    prompt: str,
    tools: list[str],
) -> tuple[int, int]:
    options = _agent_options(provider, settings, workdir, system_prompt, tools)

    with apply_env(provider):
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            turns = await _receive_turns(client, provider.model)

    return turns, 0
