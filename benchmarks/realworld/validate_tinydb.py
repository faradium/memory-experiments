from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from faradium_bench.repo import append_text, copy_repo, run_pytest

sys.path.insert(0, str(Path(__file__).parent))
from tinydb_bench import ACCEPTANCE_TEST_FILE, BASE, TASKS

REFERENCE = """

    # --- reference implementations for benchmark validation ---
    def _j(self, name):
        if not hasattr(self, "journal"):
            self.journal = []
        self.journal.append(name)

    def insert_unique(self, document, field):
        from tinydb.queries import Query
        if self.contains(Query()[field] == document.get(field)):
            return None
        out = self.insert(document)
        self._j("insert_unique")
        return out

    def pop(self, doc_id):
        doc = self.get(doc_id=doc_id)
        if doc is None:
            raise KeyError(doc_id)
        self.remove(doc_ids=[doc_id])
        self._j("pop")
        return dict(doc)

    def increment(self, cond, field, by=1):
        def op(doc):
            doc[field] = doc[field] + by
        out = self.update(op, cond)
        self._j("increment")
        return out

    def toggle(self, cond, field):
        def op(doc):
            doc[field] = not doc[field]
        out = self.update(op, cond)
        self._j("toggle")
        return out

    def rename_field(self, cond, old, new):
        def op(doc):
            if old in doc:
                doc[new] = doc.pop(old)
        out = self.update(op, cond)
        self._j("rename_field")
        return out

    def dedupe(self, field):
        seen, kill = set(), []
        for doc in self:
            if field in doc:
                if doc[field] in seen:
                    kill.append(doc.doc_id)
                else:
                    seen.add(doc[field])
        if kill:
            self.remove(doc_ids=kill)
        self._j("dedupe")
        return len(kill)

    def remove_field(self, cond, field):
        def op(doc):
            doc.pop(field, None)
        out = self.update(op, cond)
        self._j("remove_field")
        return out

    def replace(self, cond, document):
        ids = [d.doc_id for d in self.search(cond)]
        def updater(table):
            for did in ids:
                table[did] = dict(document)
        self._update_table(updater)
        self._j("replace")
        return ids
"""


def run_acceptance(repo: Path, test_code: str) -> tuple[bool, str]:
    test_file = repo / "tests" / ACCEPTANCE_TEST_FILE
    test_file.write_text(test_code)

    try:
        result = run_pytest(repo, f"tests/{ACCEPTANCE_TEST_FILE}", timeout=120)
        return result.returncode == 0, (result.stdout or "")[-500:]
    finally:
        test_file.unlink()


def main():
    tmp = Path(tempfile.mkdtemp(prefix="tinydb-val-"))
    base_repo = copy_repo(BASE, tmp / "base")
    ref_repo = copy_repo(BASE, tmp / "ref")
    append_text(ref_repo / "tinydb" / "table.py", REFERENCE)

    all_ok = True
    for task in TASKS:
        passes_on_base, _ = run_acceptance(base_repo, task["test"])
        passes_on_ref, ref_output = run_acceptance(ref_repo, task["test"])

        flag = "OK " if (not passes_on_base and passes_on_ref) else "BAD"
        if flag == "BAD":
            all_ok = False

        print(
            f"[{flag}] {task['id']}: fails_on_base={not passes_on_base} "
            f"passes_on_ref={passes_on_ref}"
        )
        if not passes_on_ref:
            print("      " + ref_output.replace("\n", "\n      ")[:400])

    suite = run_pytest(ref_repo, "tests/", timeout=300)
    print(f"base suite on ref: {'PASS' if suite.returncode == 0 else 'FAIL'}")

    shutil.rmtree(tmp, ignore_errors=True)

    print("ALL OK" if all_ok and suite.returncode == 0 else "PROBLEMS FOUND")


if __name__ == "__main__":
    main()
