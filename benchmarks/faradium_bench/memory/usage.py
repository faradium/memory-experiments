from __future__ import annotations

from collections import defaultdict

PRICES = {
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "or-laguna": {"in": 0.20, "out": 0.40, "cache_read": 0.0, "cache_write": 0.0},
    "or-laguna-s": {"in": 0.10, "out": 0.20, "cache_read": 0.0, "cache_write": 0.0},
}

_TOKENS_PER_PRICE_UNIT = 1_000_000


def _empty_totals() -> dict[str, dict[str, int]]:
    return defaultdict(lambda: defaultdict(int))


_totals_by_model: dict[str, dict[str, int]] = _empty_totals()


def _cost_usd(model: str, totals: dict[str, int]) -> float:
    prices = PRICES.get(model)
    if not prices:
        return 0.0

    return (
        totals["in"] * prices["in"]
        + totals["out"] * prices["out"]
        + totals["cache_read"] * prices["cache_read"]
        + totals["cache_write"] * prices["cache_write"]
    ) / _TOKENS_PER_PRICE_UNIT


def add(model: str, usage: dict | None) -> None:
    if not isinstance(usage, dict):
        return

    totals = _totals_by_model[model]
    totals["in"] += usage.get("input_tokens") or 0
    totals["out"] += usage.get("output_tokens") or 0
    totals["cache_read"] += usage.get("cache_read_input_tokens") or 0
    totals["cache_write"] += usage.get("cache_creation_input_tokens") or 0


def drain() -> dict:
    global _totals_by_model
    report: dict = {"models": {}, "usd": 0.0}

    for model, totals in _totals_by_model.items():
        usd = _cost_usd(model, totals)
        report["models"][model] = {**totals, "usd": round(usd, 6)}
        report["usd"] += usd

    report["usd"] = round(report["usd"], 6)
    _totals_by_model = _empty_totals()
    return report
