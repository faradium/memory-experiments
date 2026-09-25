# Faradium · Memory Research

Does memory that survives between sessions make a coding agent better, and how
should it be delivered? The write-up is [`PAPER.md`](PAPER.md); the
iteration-by-iteration log is [`docs/DEVLOG.md`](docs/DEVLOG.md).

## The benchmark

A real library (TinyDB) plus a made-up rule stated once in the first task: every
method that changes the table must append its own name to a `journal` list.
Seven ordinary tasks follow, each in a fresh session on a clean copy of the
repo, none of them mentioning the rule. A task counts as solved only if the
feature works and the rule was followed.

| Setup    | What it is                            | Seeds | Sonnet 4.6 | Laguna M.1 | Laguna S-2.1 | Cost per task (Sonnet) |
| -------- | ------------------------------------- | ----- | ---------- | ---------- | ------------ | ---------------------- |
| `raw`    | no memory at all (control)            | 3     | 0%         | 0%         | 0%           | $0.13                  |
| `native` | Claude Code's built-in memory         | 3     | 0%         | —          | —            | $0.15                  |
| `push`   | facts are put into the agent's prompt | 3–4   | 86%        | 57%        | 32%          | $0.17                  |
| `gated`  | push **+ generated checks**           | 3     | **100%**   | **81%**    | **86%**      | $1.00                  |

## Layout

| Path | What it is |
| --- | --- |
| `benchmarks/realworld/` | The TinyDB benchmark: tasks, runner, grader validators. |
| `benchmarks/faradium_bench/memory/` | The memory variants: `hermes` (push), `gate` + `autogate` (gated), `usage` (cost). |
| `benchmarks/faradium_bench/` | Harness: settings, providers (Anthropic, OpenRouter via a LiteLLM proxy), git and pytest helpers. |
| `charts/` | Per-task trajectory charts from the study. |

## Running it

```bash
cd benchmarks
cp .env.example .env        # auth and knobs
uv sync
bash realworld/run_tinydb.sh   # BENCH_AGENT_MODEL picks the agent model
uv run pytest               # harness unit tests
```

Needs Python 3.11+, [`uv`](https://docs.astral.sh/uv/) and the Claude Code CLI
on PATH; OpenRouter models also need docker for the proxy. The runner expects a
pristine TinyDB v4.8.0 checkout at `results/realworld/tinydb_base`.

## License

[MIT](LICENSE).
