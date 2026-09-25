from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

from faradium_bench.config import Settings
from faradium_bench.memory import MEMORY_SERVICE_MODEL, autogate
from faradium_bench.providers import anthropic_provider
from faradium_bench.repo import append_text, copy_repo

sys.path.insert(0, str(Path(__file__).parent))
from tinydb_bench import BASE

FACTS = [
    "Every mutating `Table` method must append its own method name (a string) to "
    "`self.journal`, a list lazily initialized on first use; this applies to any "
    "mutating method added or modified.",
    "New convenience methods on `Table` are implemented in `tinydb/table.py` and "
    "typically delegate to existing primitives like `update`/`remove`.",
]

TASK = (
    "In the `tinydb` library, add a `Table.dedupe(field)` method: remove "
    "documents whose value for `field` duplicates an earlier document's value "
    "(keep the first occurrence); return the number removed."
)

_COMMON = """diff --git a/tinydb/table.py b/tinydb/table.py
--- a/tinydb/table.py
+++ b/tinydb/table.py
@@ -700,3 +700,22 @@ class Table:
"""

DIFF_BAD_MISSING = (
    _COMMON
    + """+    def dedupe(self, field):
+        seen, kill = set(), []
+        for doc in self:
+            if field in doc:
+                if doc[field] in seen:
+                    kill.append(doc.doc_id)
+                else:
+                    seen.add(doc[field])
+        if kill:
+            self.remove(doc_ids=kill)
+        return len(kill)
"""
)

DIFF_BAD_ORDER = (
    _COMMON
    + """+    def dedupe(self, field):
+        self.journal = getattr(self, 'journal', [])
+        self.journal.append('dedupe')
+        seen, kill = set(), []
+        for doc in self:
+            if field in doc:
+                if doc[field] in seen:
+                    kill.append(doc.doc_id)
+                else:
+                    seen.add(doc[field])
+        if kill:
+            self.remove(doc_ids=kill)   # remove() appends 'remove' AFTER our entry
+        return len(kill)
"""
)

DIFF_GOOD = (
    _COMMON
    + """+    def dedupe(self, field):
+        seen, kill = set(), []
+        for doc in self:
+            if field in doc:
+                if doc[field] in seen:
+                    kill.append(doc.doc_id)
+                else:
+                    seen.add(doc[field])
+        if kill:
+            self.remove(doc_ids=kill)
+        self.journal = getattr(self, 'journal', [])
+        self.journal.append('dedupe')
+        return len(kill)
"""
)


INSTRUMENTED_REMOVE = """
    def remove(self, cond=None, doc_ids=None):
        # ... (delegates to _update_table) ...
        self.journal = getattr(self, 'journal', [])
        self.journal.append('remove')
        return removed_ids
"""

CASES = (
    ("bad-missing", DIFF_BAD_MISSING, "violated"),
    ("bad-order", DIFF_BAD_ORDER, "violated"),
    ("good", DIFF_GOOD, "applied"),
)


def build_workdir(diff: str) -> Path:
    repo = copy_repo(BASE, Path(tempfile.mkdtemp(prefix="blindspot-")) / "repo")

    hunk_body = diff.split("@@")[-1].split("\n", 1)[1]
    added_lines = "\n".join(line[1:] for line in hunk_body.splitlines() if line.startswith("+"))
    append_text(
        repo / "tinydb" / "table.py",
        "\n" + INSTRUMENTED_REMOVE + "\n" + added_lines + "\n",
    )

    return repo


async def main():
    settings = Settings.load()
    judge = anthropic_provider(MEMORY_SERVICE_MODEL, settings)

    for name, diff, expected in CASES:
        work = build_workdir(diff)
        verdicts = await autogate.judge_diff(judge, FACTS, TASK, diff, workdir=work)
        verdict = verdicts[0]["verdict"]
        flag = "OK " if verdict == expected else "MISS"

        print(
            f"[{flag}] {name}: verdict={verdict} (want {expected}) "
            f"evidence={verdicts[0]['evidence'][:140]}"
        )

        shutil.rmtree(work.parent, ignore_errors=True)

    print("BLINDSPOT_VALIDATE_DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
