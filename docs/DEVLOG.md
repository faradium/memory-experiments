# Devlog

How the benchmark in the README came to be, one iteration at a time.

**v0. SWE-bench, memory on and off (Laguna M.1 and Sonnet, 30 django tasks).**
No difference (two more tasks solved out of 30, well within noise). The tasks
had almost nothing in common (only 7 of 29 shared even one file), the memories
were written but never read, and the dataset is in the models' training data.
This shape of benchmark cannot measure memory.

**v1. Same django version, tasks in chronological order (Sonnet).** Giving
related tasks a sequence didn't help. No difference again.

**v2. A small generated repository with a trap that comes back in every task,
memory on and off.** The first clean signal, and it was negative: with memory
the agent needed about twice as many turns (17 vs 8) and solved no more tasks.

**v3. Three ways of delivering the same memory: none, a search tool, facts
put into the prompt.** The cost is not in finding the memory and only partly in
how it is delivered. A capable model rediscovers the trap in about 7 turns by
reading the code, so there is less to save than memory costs. Putting facts into
the prompt beats the search tool.

**v4. A nastier trap: a decoy API and two hidden requirements.** It collapsed.
The model reads the source and solves it in about 8 turns no matter how
misleading the trap is. Memory cannot win on anything that can be read from the
code.

**v5. Push memory (inspired by the Hermes agent): facts stored as plain text,
summarized after each session, put into the next session's prompt.** The first
memory that wasn't a net loss. Roughly the same cost, and visibly less
re-exploring.

**v6. A rule told once and written nowhere in the code.** This is what memory is
for, and the pushed facts were ignored: 0 of 7 tasks when the rule sat in the
system prompt, 0 of 7 when it was put right next to the task as an order. The
wall is not storing, finding or placing the memory. It is getting the agent to
act on it.

**v7. Enforcement: a check derived from the memory, with the failure fed back.**
0 of 7 became 7 of 7. Repeated five times: push got under one task in seven on
average, the checked version got all seven every time.

**v8. Generating the checks automatically.** Stored facts are turned into
pytest checks by a model and validated against the untouched repository, with a
model acting as judge for facts that can't be tested. Still 7 of 7, with no
hand-written checks anywhere.

**v9. A real repository (TinyDB) with a planted journal rule.** The first run
was invalid for a reason I did not expect: Claude Code's own per-project memory,
keyed by the working directory, carried the rule into the no-memory control,
which scored an impossible 6 of 7. Fixed by giving every task its own unique
directory. After nine seeds: no memory 0%, push and checks tied at 65%, checks
at about five times the cost.

**v10. Reading the failed sessions overturned the tie.** My test demanded more
than the rule said (the method name had to be the last journal entry, not just
present). Grading again against the rule as stated converted half of the checked
version's failures. Faithful numbers on the final-protocol seeds: checks 96%,
push 89%. Lesson: make sure the test says the same thing as the rule, not just
that it fails before the fix and passes after.

**v11. Confirmation run with the fixed grader, plus Claude Code's built-in
memory as an arm.** No memory 0%, built-in memory 0% (the agent never once
chose to save the rule), push 86%, checks 100% (21 of 21).

**v12. A second model family: Laguna M.1, three seeds.** No memory 0%, push
57%, checks 81%. Laguna followed the pushed rule less often than Sonnet, so
the checks added more for it, but they did not bring it all the way.

**v13. Reading the Laguna sessions.** Checks can amplify a memory mistake. A
style observation ("field-level operations belong in operations.py") had been
saved as a rule, the check enforced it, and the agent obeyed the check over the user's
explicit request. Memory needs to know where a fact came from (stated rule or
observed habit), and the task in front of the agent must always win.

**v14 to v17. Mining and then correcting the transcript analysis.** An
automated pass suggested Laguna spends about half its actions after its last
edit and that a passing check makes it stop sooner. Reading the sessions by hand
caught two errors: some "failures" were sessions the harness had graded too
early while a subagent was still running, and the CLI writes one log entry per
content block, inflating naive turn and token counts about five times. After
correction, what fills the long tails is competent self-diagnosis that never
turns into an edit.

**v18. Correction of v14.** The "checks make it stop sooner" claim was an
artefact of dividing by longer sessions. In absolute terms the wind-down after
the last edit is a fixed per-model amount, about ten times larger for Laguna
M.1 than for Sonnet, and it does not change with how memory is delivered. The
difference between models stands; the effect of the checks on it does not.

**v19. A third model: Laguna S-2.1, three seeds (four for push).** No memory
0%, push 32%, checks 86%. The three tasks it failed with checks on, one per
seed, share one shape: the model explores, writes down a correct plan, announces
it will implement it, and then prints the same forty lines of `table.py` dozens
to hundreds of times until it runs out of turns, without editing a single line.
Its wind-down after the last edit sits between Sonnet's and M.1's and, again,
does not move with memory.
