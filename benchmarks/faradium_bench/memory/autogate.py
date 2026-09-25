from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..providers import Provider
from ..repo import copy_repo, run_pytest
from . import llm


@dataclass
class Check:
    fact: str
    kind: str
    test_code: str | None = None
    meta: dict = field(default_factory=dict)


_VERDICTS = ("applied", "violated", "not-applicable")

_MAX_FILE_CHARS = 4000
_GENERATE_SOURCE_BUDGET = 20_000
_JUDGE_SOURCE_BUDGET = 16_000
_MAX_JUDGE_DIFF_CHARS = 8000
_ONE_SHOT_MAX_TURNS = 8

_GENERATE = (
    "You convert remembered facts about ONE code repository into enforceable checks "
    "for future coding sessions on it. "
    "You have NO tools — everything you need is below; respond with the JSON only."
    "\n\n"
    "REPOSITORY SOURCE:\n"
    "{files}"
    "\n\n"
    "For EACH fact below, decide:\n"
    '- kind="test" if the fact states a concrete, machine-checkable property of the code '
    "that a small pytest can verify using only the repo's own public API (no new dependencies). "
    "Then write that pytest: self-contained, ONE test function, assertion messages that quote "
    "the convention. "
    "The test must verify the GENERAL rule (use existing/base features of the repo, not "
    "task-specific values), so it stays valid for any future task.\n"
    '- kind="judge" if the fact is advisory, stylistic, about process, or not reliably '
    "checkable by running code."
    "\n\n"
    "Return ONLY a JSON array, one object per fact, in order:\n"
    '[{{"kind": "test", "test_code": "..."}} or {{"kind": "judge"}}]'
    "\n\n"
    "FACTS:\n"
    "{facts}\n"
)

_JUDGE = (
    "You audit a code change for compliance with remembered project conventions. "
    "You have NO tools — everything you need is below; respond with the JSON only. "
    "Be precise and evidence-based."
    "\n\n"
    "TASK GIVEN TO THE CODING AGENT:\n"
    "{task}"
    "\n\n"
    "CURRENT REPOSITORY SOURCE (after the change):\n"
    "{source}"
    "\n\n"
    "GIT DIFF OF ITS CHANGE:\n"
    "{diff}"
    "\n\n"
    "CONVENTIONS (remembered from prior sessions):\n"
    "{facts}"
    "\n\n"
    "For EACH convention, in order, return a verdict. Two rules:\n"
    "1. APPLICABILITY FIRST: a convention is exercised ONLY if completing THIS task required "
    "creating or modifying code in the convention's scope. "
    "If the diff touches no code in that scope (e.g. docs-only, comment-only, unrelated "
    'module), the verdict is "not-applicable" — even if the current source does not '
    "implement the convention. "
    "You audit THIS change, not the whole repo.\n"
    "2. OMISSION COUNTS: when the convention IS exercised, check the current source, not just "
    "the diff — if the task's change should have added or preserved something the convention "
    "demands and the source lacks it, that is a violation.\n"
    "3. TRACE EXECUTION ORDER: when a convention concerns the order or final state of a side "
    "effect (e.g. appending a name, logging, counters), mentally execute the new code "
    "INCLUDING the methods it delegates to (their source is above). "
    "If a delegated call performs the same side effect AFTER the new code's own contribution, "
    "the final state reflects the delegate — verify that still satisfies the convention.\n"
    '- "applied": the current code satisfies it where this task exercises it (cite the lines)\n'
    '- "violated": this task exercises the convention and the current code does not honor it '
    "(cite what is missing and where it should be)\n"
    '- "not-applicable": this convention is not exercised by this task/change'
    "\n\n"
    "Return ONLY a JSON array:\n"
    '[{{"verdict": "applied|violated|not-applicable", "evidence": "..."}}]\n'
)


async def _one_shot(provider: Provider, prompt: str, model: str | None = None) -> str:
    return await llm.complete(provider, prompt, model=model, max_turns=_ONE_SHOT_MAX_TURNS)


def _parse_json_array(text: str) -> list[dict]:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []

    return parsed if isinstance(parsed, list) else []


def _item_at(items: list, index: int) -> dict:
    if index < len(items) and isinstance(items[index], dict):
        return items[index]
    return {}


def _numbered(facts: list[str]) -> str:
    return "\n".join(f"{number}. {fact}" for number, fact in enumerate(facts, start=1))


def _inline_source(repo: Path, budget: int, include_tests: bool) -> str:
    parts = []
    for path in sorted(repo.rglob("*.py")):
        if ".venv" in path.parts or (not include_tests and "tests" in path.parts):
            continue
        source = path.read_text()[:_MAX_FILE_CHARS]
        parts.append(f"--- {path.relative_to(repo)} ---\n{source}")
        budget -= len(source)
        if budget <= 0:
            break

    return "\n".join(parts)


def _test_check_from_spec(base_repo: Path, fact: str, spec: dict) -> Check | None:
    test_code = spec.get("test_code")
    if spec.get("kind") != "test" or not test_code:
        return None

    validation = validate_test(base_repo, test_code)
    if not validation["collects"]:
        return None

    return Check(fact=fact, kind="test", test_code=test_code, meta=validation)


def _check_priority(check: Check) -> int:
    if check.kind != "test":
        return 2
    return 0 if check.meta.get("fails_on_base") else 1


def validate_test(base_repo: Path, test_code: str) -> dict:
    temp_dir = Path(tempfile.mkdtemp(prefix="autogate-"))
    try:
        repo_copy = copy_repo(base_repo, temp_dir / "repo")

        test_file = repo_copy / "tests" / "_autogate.py"
        test_file.parent.mkdir(exist_ok=True)
        test_file.write_text(test_code)

        collect_result = run_pytest(repo_copy, "tests/_autogate.py", timeout=60, collect_only=True)
        if collect_result.returncode not in (0, 1):
            return {"collects": False, "fails_on_base": False}

        run_result = run_pytest(repo_copy, "tests/_autogate.py", timeout=120)
        return {"collects": True, "fails_on_base": run_result.returncode != 0}
    except Exception:
        return {"collects": False, "fails_on_base": False}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def generate_checks(
    provider: Provider, facts: list[str], base_repo: Path, max_checks: int = 4
) -> list[Check]:
    if not facts:
        return []

    files = _inline_source(base_repo, budget=_GENERATE_SOURCE_BUDGET, include_tests=True)
    batch_reply = await _one_shot(provider, _GENERATE.format(files=files, facts=_numbered(facts)))
    batch_specs = _parse_json_array(batch_reply)

    checks: list[Check] = []
    for index, fact in enumerate(facts):
        check = _test_check_from_spec(base_repo, fact, _item_at(batch_specs, index))
        if check is None:
            retry_reply = await _one_shot(
                provider, _GENERATE.format(files=files, facts=f"1. {fact}")
            )
            check = _test_check_from_spec(
                base_repo, fact, _item_at(_parse_json_array(retry_reply), 0)
            )
        checks.append(check or Check(fact=fact, kind="judge"))

    checks.sort(key=_check_priority)
    return checks[:max_checks]


async def judge_diff(
    provider: Provider,
    facts: list[str],
    task_prompt: str,
    diff: str,
    workdir: Path | None = None,
    model: str | None = None,
) -> list[dict]:
    if not facts:
        return []

    changed_paths = re.findall(r"^diff --git a/(\S+)", diff, re.MULTILINE)
    if changed_paths and not any(path.endswith(".py") for path in changed_paths):
        return [{"verdict": "not-applicable", "evidence": "no code files changed"} for _ in facts]

    source = (
        _inline_source(workdir, budget=_JUDGE_SOURCE_BUDGET, include_tests=False)
        if workdir
        else "(not provided)"
    )

    reply = await _one_shot(
        provider,
        _JUDGE.format(
            task=task_prompt,
            source=source,
            diff=diff[:_MAX_JUDGE_DIFF_CHARS],
            facts=_numbered(facts),
        ),
        model=model,
    )
    replies = _parse_json_array(reply)

    verdicts = []
    for index in range(len(facts)):
        spec = _item_at(replies, index)
        verdict = spec.get("verdict", "not-applicable")
        if verdict not in _VERDICTS:
            verdict = "not-applicable"
        verdicts.append({"verdict": verdict, "evidence": spec.get("evidence", "")})

    return verdicts
