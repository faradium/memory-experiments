# Faradium memory system - postmortem / write-up

**TLDR:** Insights I've found building a memory system for coding agents. The system was built on the assumption that coding memories should store experiences rather than raw facts, which usually could just be retrieved from the implementation. What I learned along the way is the intuition on how agents behave when given memory tools and have to avoid these shortcomings.

The first finding aligns with observations I've encountered in my earlier research projects: given custom tools, agents almost never use them. When forced to use them, they call them as prompted, but ignore the results. In effect, pushing memorized facts straight into the agent's prompt works far better and costs much less. Another observation is very fundamental: memory can't help with anything the agent can read from the code and in this case memory starts to be an overhead. It only pays off for things that were told / experienced once and not written anywhere, so the final benchmark is built to test this. In cases where the agent decides not to act on memories, turning memories into automated tests closes the gap.

## Initial vision

At the beginning of this year, as a part of the `Faradium` project, I started working on a system intended to support long-running agents. The thesis was that the main bottleneck is lack of persistent memory. Without it agents started falling into the same traps over and over again: reimplementing previously encountered bugs, forgetting about coding conventions, etc. Also with time they simply start to forget their main objective. It wasn't just a hypothesis, I've experienced it personally. It's especially visible when working on esoteric libraries or private codebases. In these environments agents spend most of their time exploring, then they fix the error, but the context window gets filled and on a subsequent task they have to reexplore, often falling into the same traps again.

This obviously calls for a good memory system, and there are already many projects that aim to solve this: Hermes agent with its own three-layer memory system, mem0 with its graph memory and many more simpler approaches like keeping notes in Obsidian or just explicitly prompting agents to use markdown files to record memories.

Despite all of these different approaches, they all seem to fall into the same category, which is not an ideal choice for coding: they mostly rely on saving facts, which in a programming context get obsolete fast. On top of that, most facts worth memorizing are already written down in the code itself. The code is always up to date, while a memory of it is a fragile copy that can only get older. An agent acting on an outdated fact is worse than one with no memory at all.

The idea behind this memory system was to fill the gap and build robust coding memory. Turns out the most important outcome of this project became not the memory system itself, but the intuition and understanding on how and when agents actually use it.

## Memory implementation

Instead of memorizing facts the idea was to record the pitfalls, failures, successes, wrong assumptions. This way we avoid memorizing implementation details and focus on aspects that should remain relevant for much longer. The agent was given four tools: three to save memories (a mistake, a decision or a finding) and one to search them. It was up to the agent to decide when to use them.

The first opportunity to confront my assumptions and gather feedback came when I attended a YC event in Paris. It was a perfect place for such a survey: many developers and very high density of agentic programming powerusers. Out of these conversations I could highlight a few questions / doubts:

- Most projects are already in development and a memory system will rather be added midway through the process. Will your system handle this well?
- Most projects consist of many programmers working in parallel. Some could have the memory system turned on and others not. Is this a problem?

In theory, focusing on experience memories solves these problems much better than a memory of facts. The answer to the second question highlights the real value. Experience memory is implementation agnostic, which makes it possible to build one memory store that whole development teams can share. With more agents sharing traps they encountered, other agents could use this knowledge to avoid them.

All of this sounded like a great idea, but will it work in practice...

## Benchmark evolution

I could not find any good benchmark for agentic memory, so I had to make one myself. The first benchmark iteration was to run SWE-bench instances sequentially, so that memories saved while solving one task could help with the next ones, and to compare the results with memory turned on and off. In the first variation all tasks came from a single repository (django), but they turned out to have almost nothing in common, so there was very little value in memory. In the second iteration, I picked tasks from the same django version and ran them in chronological order (sorting by commit dates), to give memory the best possible chance. In both cases memory made no measurable difference.

Implementation revealed something much more interesting and it was a problem with my optimistic assumption: agents will use given tools wisely. When benchmarks didn't improve, I started digging into what happened and the first metric I've checked was how often tools were used -- turns out... they were not. Only after I explicitly told the agent to use them they eventually started calling them. The agent was now calling the tools, but it searched the memory just because it was told to, not because it saw some value in it.

The benchmark had to change before it could measure anything. Since SWE-bench tasks had nothing to carry from one to the next, I generated a small repository with a trap that was replanted at every task, but this time... it was too easy: a capable agent simply finds the trap by reading the code, no need for expensive tool calling. Memory cannot win on anything that can be read from the code.

So the final version tests the opposite case: a rule that is told to the agent once and is not written anywhere in the code. I took a real open-source project (TinyDB) and in the first task, next to a normal feature request, stated a rule: every method that changes the table has to append its own name to a `journal` list. Then followed seven ordinary tasks that never mentioned the rule again. Each task starts in a fresh session on a clean copy of the repository, so nothing from the earlier tasks survives in the code, and a task counts as solved only if the feature works and the new method shows up in the journal. The rule is written nowhere, so the only way to keep following it is to remember it was told.

The memory system changed along the way as well. I started with the experience memory described above, later tested a `push` memory (inspired by the Hermes agent), which stores plain facts and puts them into the agent's prompt, and followed up with a memory system that, instead of only storing memories, also generates automated checks that are meant to catch if they are not followed, later called `gated memory`. Regarding what was stated in the introduction, the results below come from a factual memory, not from the experience memory I originally set out to build. The next step was meant to push experiences into the prompt in the same way, but I didn't have time to implement it.

This is how the two memory variants work. `push` is the left branch only; `gated` is both:

```
                ┌──────────────┐
  session ends ─►  summarizer  ├─► facts (memory store)
                └──────────────┘         │
                            ┌────────────┴─────────────┐
                            ▼                          ▼
                   pushed into the           compiled into checks
                   next agent's prompt       (tests, or a judge)
                            │                          │
                            ▼                          │
                     agent does the task               │
                            │                          │
                            ▼                          ▼
                     agent says "done" ────────► checks run ──► pass → done
                            ▲                          │
                            └── failure fed back ──────┘
```

For a while the benchmark suggested the checks were useless: they performed similarly with plain push variant at several times the cost. The reason turned out to be my own test, which checked something slightly stricter than the rule actually stated. It punished exactly the agents that followed the rule most precisely. Once the test was fixed, the gated memory came out ahead.

The table below shows how often those later tasks followed the rule in different memory variants.

| Setup    | What it is                            | Seeds | Sonnet 4.6 | Laguna M.1 | Laguna S-2.1 | Cost per task (Sonnet) |
| -------- | ------------------------------------- | ----- | ---------- | ---------- | ------------ | ---------------------- |
| `raw`    | no memory at all (control)            | 3     | 0%         | 0%         | 0%           | **$0.13**              |
| `native` | Claude Code's built-in memory         | 3     | 0%         | ---        | ---          | $0.15                  |
| `push`   | facts are put into the agent's prompt | 3-4   | 86%        | 57%        | 32%          | $0.17                  |
| `gated`  | push **+ generated checks**           | 3     | **100%**   | **81%**    | **86%**      | $1.00                  |

## Findings

Every variant is told the same rule, once. What surprised me is where the difficulty turned out to be: not in storing the rule or finding it, but in getting the agent to use something that's in front of it. Main findings are:

- In Claude Code's built-in memory variant the rule was never carried over: agent followed the rule when it was told about it, but never decided to save it for later.
- Giving the agent memory tools is not enough. Pushing the remembered facts directly into its prompt works much better and costs little.
- The hard part is making the agent act on it: even with the rule in its prompt, the agent sometimes drops it, because the task at hand never asks about it.
- Turning memories into automated checks closes this gap. Sonnet then followed the rule every time, but at around six times the cost.
- Memory does not help with anything the agent can simply read from the code.

## Bonus

Manually reading the session trajectories (Sonnet and both Laguna models) turned up one more thing. After its last edit, Laguna keeps going for much longer than Sonnet does (roughly four to ten times more output, depending on the Laguna model), and it stays consistent with memory variants. The hesitation tail simply seems to be a model characteristic. The Laguna model looks to be more hesitant to mark given task as DONE. Trajectories showed it's testing some edge-cases, theories and iterating on them. Whether this comes from the training or something else, I can't really tell.

Trajectories of the three tasks Laguna S-2.1 failed show the same characteristic. In each of them the model explored the code, wrote down a correct plan (add the method, append to the journal), announced "let me implement the changes", but eventually never did. It printed the same forty lines of `table.py` dozens of times, reannounced the plan, and ran out of its turn budget without changing a single line, while the check kept correctly reporting that the rule was not met.

| Output after the last edit (tokens, avg.) | `raw`  | `push` | `gated` |
| ----------------------------------------- | ------ | ------ | ------- |
| Sonnet 4.6                                | ~400   | ~350   | ~430    |
| Laguna M.1                                | ~3,700 | ~4,400 | ~3,600  |
| Laguna S-2.1                              | ~1,600 | ~1,700 | ~2,100  |

## Future work

The first thing to do is the step I didn't have time for: putting experience memory into the agent's prompt, to see if the original idea of remembering experiences holds up in practice.

There is something even more interesting. Recent release of the Jev model sparked an idea that it can be a great tool for an effective memory system. Jev does not write text, it makes quick decisions and they are much cheaper than generating structured output with LLMs. So instead of using expensive language model, Jev could decide what to remember from the transcripts, what to remove from the memory, whether the agent's work follows a remembered rule and what memories are worth pushing to the agent's context. This is set to be the future direction of the Faradium project, which is what I'm currently working on.
