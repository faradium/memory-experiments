from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from faradium_bench.config import Settings
from faradium_bench.memory import MEMORY_SERVICE_MODEL, autogate, gate, hermes, usage
from faradium_bench.providers import Provider, anthropic_provider, openrouter_provider
from faradium_bench.proxy import ensure_proxy_for
from faradium_bench.repo import (
    captured_output,
    copy_repo,
    git_diff,
    init_repo,
    reset_repo,
    run_pytest,
    tail_lines,
    temporary_test_file,
)

sys.path.insert(0, str(Path(__file__).parent))
from tinydb_bench import ACCEPTANCE_TEST_FILE, BASE, TASKS

BENCH = Path(__file__).resolve().parent.parent


AGENT_MODEL = os.environ.get("BENCH_AGENT_MODEL", "claude-sonnet-4-6")
_SUFFIX = (
    "" if AGENT_MODEL.startswith("claude") else "_" + AGENT_MODEL.split("/")[-1].replace(".", "-")
)
OUT = BENCH / "results" / "realworld" / f"tinydb_run{_SUFFIX}"
STORE = str(OUT / "facts.db")

PRESET = {"type": "preset", "preset": "claude_code"}
TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]

ARMS = ("raw", "hermes", "gated", "native")
MEMORY_ARMS = ("hermes", "gated")


@dataclass(frozen=True)
class Backends:
    settings: Settings
    agent: Provider
    helper: Provider
    judge: Provider


def make_workdir(arm: str, rep: int, task_id: str) -> Path:
    work = OUT / "work" / f"{arm}-r{rep}-{task_id}"
    if work.exists():
        shutil.rmtree(work)
    work.parent.mkdir(parents=True, exist_ok=True)
    copy_repo(BASE, work)
    init_repo(work)

    return work


def purge_cli_memory(work: Path) -> None:
    slug = str(work).replace("/", "-")
    shutil.rmtree(Path.home() / ".claude" / "projects" / slug / "memory", ignore_errors=True)


def reset_shared_workdir(work: Path) -> None:
    reset_repo(work)


def capture_diff(work: Path) -> str:
    return git_diff(work)


def grade(work: Path, test_code: str) -> tuple[bool, str]:
    with temporary_test_file(work, ACCEPTANCE_TEST_FILE, test_code):
        try:
            result = run_pytest(work, "tests/", timeout=300)

            passed = result.returncode == 0
            tail = "" if passed else tail_lines(captured_output(result), 15)
            return passed, tail
        except Exception as exc:
            return False, f"grader error: {exc}"


def prepare_workdir(arm: str, rep: int, task_index: int, task_id: str) -> Path:
    if arm != "native":
        return make_workdir(arm, rep, task_id)

    shared = OUT / "work" / f"native-r{rep}"
    if task_index == 0:
        if shared.exists():
            shutil.rmtree(shared)
        purge_cli_memory(shared)
        seeded = make_workdir("native-shared", rep, "seed")
        shutil.move(str(seeded), str(shared))
    else:
        reset_shared_workdir(shared)

    return shared


async def run_task_session(
    backends: Backends, arm: str, work: Path, task_prompt: str
) -> tuple[list[str], str, int, int]:
    facts: list[str] = []
    system_prompt = PRESET

    if arm in MEMORY_ARMS:
        facts = hermes.retrieve(STORE, task_prompt, limit=8)
        block = hermes.memory_block(facts)
        system_prompt = {**PRESET, "append": block} if block else PRESET

    if arm == "gated":
        checks = await autogate.generate_checks(backends.helper, facts, BASE)
        kinds = ",".join(check.kind for check in checks) or "-"
        turns, cycles = await gate.run_gated_session(
            backends.agent,
            backends.settings,
            work,
            system_prompt,
            task_prompt,
            TOOLS,
            checks=checks,
            judge_provider=backends.judge,
        )
    else:
        kinds = "-"
        turns, cycles = await gate.run_push_session(
            backends.agent,
            backends.settings,
            work,
            system_prompt,
            task_prompt,
            TOOLS,
        )

    return facts, kinds, turns, cycles


def append_record(results_path: Path, record: dict) -> None:
    with open(results_path, "a") as handle:
        handle.write(json.dumps(record) + "\n")


async def run_arm(backends: Backends, arm: str, rep: int, tasks: list[dict]) -> None:
    hermes.reset_store(STORE)
    print(f"===== REPEAT {rep} ARM {arm} ({len(tasks)} tasks) =====", flush=True)
    results_path = OUT / f"{arm}_results.jsonl"

    for task_index, task in enumerate(tasks):
        seed_attempts = 3 if task_index == 0 else 1
        usage.drain()

        for attempt in range(seed_attempts):
            work = prepare_workdir(arm, rep, task_index, task["id"])
            facts, kinds, turns, cycles = await run_task_session(
                backends, arm, work, task["prompt"]
            )
            success, fail_detail = grade(work, task["test"])
            diff = capture_diff(work)

            if success or attempt == seed_attempts - 1:
                break

            print(
                f"[r{rep}|{arm}] {task['id']}: seed attempt {attempt + 1} failed — retrying",
                flush=True,
            )
            shutil.rmtree(work, ignore_errors=True)

        if task_index == 0 and not success and arm != "raw":
            print(
                f"[r{rep}|{arm}] SEED FAILED after retries — aborting arm "
                f"(seed invalid, exclude from analysis)",
                flush=True,
            )
            append_record(
                results_path,
                {
                    "repeat": rep,
                    "arm": arm,
                    "task": task["id"],
                    "success": False,
                    "turns": turns,
                    "injected": 0,
                    "gate_cycles": cycles,
                    "checks": kinds,
                    "new_facts": 0,
                    "seed_attempts": attempt + 1,
                    "arm_aborted": True,
                    "usd": usage.drain()["usd"],
                },
            )
            break

        new_facts = 0
        if arm in MEMORY_ARMS and success and diff.strip():
            learned = await hermes.summarize(backends.helper, task["prompt"], diff)
            new_facts = hermes.record_facts(STORE, task["id"], learned)

        spent = usage.drain()
        append_record(
            results_path,
            {
                "repeat": rep,
                "arm": arm,
                "task": task["id"],
                "success": success,
                "turns": turns,
                "injected": len(facts),
                "gate_cycles": cycles,
                "checks": kinds,
                "new_facts": new_facts,
                "seed_attempts": attempt + 1,
                "fail_detail": fail_detail or None,
                "usd": spent["usd"],
                "usage": spent["models"],
            },
        )
        print(
            f"[r{rep}|{arm}] {task['id']}: success={success} turns={turns} "
            f"injected={len(facts)} cycles={cycles} usd=${spent['usd']:.4f}",
            flush=True,
        )

        if success and arm != "native":
            shutil.rmtree(work, ignore_errors=True)
        elif not success and arm == "native":
            snapshot = OUT / "work" / f"native-r{rep}-FAIL-{task['id']}"
            shutil.rmtree(snapshot, ignore_errors=True)
            shutil.copytree(work, snapshot)


def load_backends() -> Backends:
    settings = Settings.load()
    if AGENT_MODEL.startswith("claude"):
        agent = anthropic_provider(AGENT_MODEL, settings)
    else:
        agent = openrouter_provider(AGENT_MODEL, settings)
        ensure_proxy_for(agent, settings)

    helper = anthropic_provider(MEMORY_SERVICE_MODEL, settings)
    judge = anthropic_provider(MEMORY_SERVICE_MODEL, settings)

    return Backends(settings=settings, agent=agent, helper=helper, judge=judge)


def selected_arms() -> list[str]:
    requested = os.environ.get("SYNTH_ARMS")
    if not requested:
        return list(ARMS)

    wanted = {name.strip() for name in requested.split(",")}
    return [arm for arm in ARMS if arm in wanted]


async def main():
    backends = load_backends()
    OUT.mkdir(parents=True, exist_ok=True)
    limit = int(os.environ.get("SYNTH_LIMIT") or len(TASKS))
    tasks = TASKS[:limit]
    arms = selected_arms()
    repeats = int(os.environ.get("SYNTH_REPEATS") or 1)
    rep_offset = int(os.environ.get("SYNTH_REP_OFFSET") or 0)

    if rep_offset == 0:
        for arm in arms:
            (OUT / f"{arm}_results.jsonl").write_text("")

    for rep in range(rep_offset, rep_offset + repeats):
        for arm in arms:
            await run_arm(backends, arm, rep, tasks)

    print("TINYDB_COMPLETE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
