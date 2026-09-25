from __future__ import annotations

import os
import re
import sqlite3

from ..providers import Provider
from . import llm

_MIN_FACT_CHARS = 10
_MAX_FACTS_PER_SUMMARY = 3
_MAX_DIFF_CHARS = 4000

_SUMMARIZE = (
    "You maintain a lightweight fact memory about ONE specific code repository, "
    "for future agents working on it. "
    "Given a task and the diff that solved it, extract 1-3 SHORT, GENERAL, reusable facts "
    "about how THIS repo works that would help a future agent do a *similar but different* "
    "task faster — e.g. non-obvious required steps, where things must be registered, "
    "silent pitfalls. "
    "Write the general rule, NOT this task's specific values (don't mention the specific "
    "transform name/behavior). "
    "Output ONLY the facts, one per line, no numbering, no preamble, no commentary."
    "\n\n"
    "TASK:\n"
    "{task}"
    "\n\n"
    "DIFF THAT SOLVED IT:\n"
    "{diff}\n"
)


def _open_store(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS facts USING fts5(text, trust UNINDEXED, src UNINDEXED)"
    )
    return connection


def _search_terms(query_text: str) -> list[str]:
    return sorted({term for term in re.findall(r"[A-Za-z_]{3,}", query_text.lower())})


def _search_facts(connection: sqlite3.Connection, terms: list[str], limit: int) -> list[tuple[str]]:
    if not terms:
        return []

    try:
        return connection.execute(
            "SELECT text FROM facts WHERE facts MATCH ? ORDER BY bm25(facts), trust DESC LIMIT ?",
            (" OR ".join(terms), limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []


def _most_trusted_facts(connection: sqlite3.Connection, limit: int) -> list[tuple[str]]:
    return connection.execute(
        "SELECT text FROM facts ORDER BY trust DESC LIMIT ?", (limit,)
    ).fetchall()


def _fact_lines(text: str) -> list[str]:
    facts = [line.strip("-*# \t") for line in text.splitlines() if line.strip()]
    return [fact for fact in facts if len(fact) >= _MIN_FACT_CHARS]


def reset_store(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)


def record_facts(path: str, source_task_id: str, facts: list[str]) -> int:
    connection = _open_store(path)
    added = 0

    for raw_fact in facts:
        fact = raw_fact.strip()
        if len(fact) < _MIN_FACT_CHARS:
            continue
        existing = connection.execute("SELECT rowid FROM facts WHERE text = ?", (fact,)).fetchone()
        if existing:
            connection.execute("UPDATE facts SET trust = trust + 1 WHERE rowid = ?", (existing[0],))
        else:
            connection.execute(
                "INSERT INTO facts(text, trust, src) VALUES (?, 1, ?)", (fact, source_task_id)
            )
            added += 1

    connection.commit()
    connection.close()
    return added


def retrieve(path: str, query_text: str, limit: int = 8) -> list[str]:
    if not os.path.exists(path):
        return []

    connection = _open_store(path)
    rows = _search_facts(connection, _search_terms(query_text), limit)
    if not rows:
        rows = _most_trusted_facts(connection, limit)

    connection.close()
    return [row[0] for row in rows]


def memory_block(facts: list[str]) -> str | None:
    if not facts:
        return None

    bullet_lines = "\n".join(f"- {fact}" for fact in facts)
    return (
        "## Project memory (facts learned by prior agents working on THIS repo)\n"
        "These were recorded from earlier successful sessions on this exact codebase. "
        "Treat them as reliable, repo-specific knowledge and use them to avoid "
        "rediscovering non-obvious steps."
        "\n\n"
        f"{bullet_lines}\n"
    )


async def summarize(provider: Provider, task_prompt: str, diff: str) -> list[str]:
    prompt = _SUMMARIZE.format(task=task_prompt, diff=diff[:_MAX_DIFF_CHARS])

    try:
        text = await llm.complete(provider, prompt, max_turns=1)
    except Exception:
        return []

    return _fact_lines(text)[:_MAX_FACTS_PER_SUMMARY]
