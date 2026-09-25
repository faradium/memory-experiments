from __future__ import annotations

from claude_agent_sdk import ClaudeAgentOptions, query

from ..providers import Provider, apply_env
from . import usage


async def complete(
    provider: Provider, prompt: str, *, model: str | None = None, max_turns: int
) -> str:
    options = ClaudeAgentOptions(
        model=model or provider.model, allowed_tools=[], max_turns=max_turns
    )
    text = ""

    with apply_env(provider):
        async for message in query(prompt=prompt, options=options):
            if type(message).__name__ == "ResultMessage":
                text = getattr(message, "result", "") or ""
                usage.add(options.model, getattr(message, "usage", None))

    return text
