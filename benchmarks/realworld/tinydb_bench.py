from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "results" / "realworld" / "tinydb_base"
ACCEPTANCE_TEST_FILE = "test_acceptance.py"

CONVENTION = (
    ' NOTE — this project has a mandatory convention ("the operation journal"): '
    "every mutating `Table` method must append its own method name (a string) to "
    "`self.journal`, a list lazily initialized on first use (e.g. "
    "`getattr(self, 'journal', ...)` or init in the method). This applies to any "
    "mutating method you add or modify."
)

_TEST_HEADER = "from tinydb import TinyDB, Query\nfrom tinydb.storages import MemoryStorage\n\n"


_SPECS = [
    (
        "insert_unique",
        "add a `Table.insert_unique(document, field)` method: insert `document` only "
        "if no existing document has the same value for `field`; return the new doc_id, "
        "or None (without inserting) if a duplicate exists",
        """db = TinyDB(storage=MemoryStorage); t = db.table('x')
    a = t.insert_unique({'u': 'ann', 'n': 1}, 'u')
    assert isinstance(a, int)
    assert t.insert_unique({'u': 'ann', 'n': 2}, 'u') is None
    assert len(t) == 1
    assert 'insert_unique' in t.journal""",
    ),
    (
        "pop",
        "add a `Table.pop(doc_id)` method: remove the document with the given doc_id "
        "and return it as a dict; raise KeyError if it does not exist",
        """db = TinyDB(storage=MemoryStorage); t = db.table('x')
    ids = t.insert_multiple([{'a': 1}, {'a': 2}])
    doc = t.pop(ids[0])
    assert doc['a'] == 1 and len(t) == 1
    try:
        t.pop(9999); assert False, 'expected KeyError'
    except KeyError:
        pass
    assert 'pop' in t.journal """,
    ),
    (
        "increment",
        "add a `Table.increment(cond, field, by=1)` method: add `by` to the numeric "
        "`field` of every document matching `cond`; return the list of updated doc_ids",
        """db = TinyDB(storage=MemoryStorage); t = db.table('x')
    t.insert_multiple([{'k': 'a', 'n': 1}, {'k': 'b', 'n': 5}])
    q = Query()
    ids = t.increment(q.k == 'a', 'n', by=2)
    assert len(ids) == 1
    assert t.get(q.k == 'a')['n'] == 3 and t.get(q.k == 'b')['n'] == 5
    assert 'increment' in t.journal """,
    ),
    (
        "toggle",
        "add a `Table.toggle(cond, field)` method: boolean-negate `field` on every "
        "document matching `cond`; return the list of updated doc_ids",
        """db = TinyDB(storage=MemoryStorage); t = db.table('x')
    t.insert_multiple([{'k': 'a', 'on': True}, {'k': 'b', 'on': False}])
    q = Query()
    t.toggle(q.k == 'a', 'on'); t.toggle(q.k == 'b', 'on')
    assert t.get(q.k == 'a')['on'] is False and t.get(q.k == 'b')['on'] is True
    assert 'toggle' in t.journal """,
    ),
    (
        "rename_field",
        "add a `Table.rename_field(cond, old, new)` method: for every document "
        "matching `cond` that has field `old`, move its value to field `new` and "
        "remove `old`; return the list of updated doc_ids",
        """db = TinyDB(storage=MemoryStorage); t = db.table('x')
    t.insert_multiple([{'k': 'a', 'old': 7}, {'k': 'b', 'x': 1}])
    q = Query()
    t.rename_field(q.k == 'a', 'old', 'new')
    d = t.get(q.k == 'a')
    assert d.get('new') == 7 and 'old' not in d
    assert 'rename_field' in t.journal """,
    ),
    (
        "dedupe",
        "add a `Table.dedupe(field)` method: remove documents whose value for `field` "
        "duplicates an earlier document's value (keep the first occurrence; documents "
        "missing `field` are kept); return the number removed",
        """db = TinyDB(storage=MemoryStorage); t = db.table('x')
    t.insert_multiple([{'u': 'a'}, {'u': 'b'}, {'u': 'a'}, {'z': 1}])
    removed = t.dedupe('u')
    assert removed == 1 and len(t) == 3
    assert 'dedupe' in t.journal """,
    ),
    (
        "remove_field",
        "add a `Table.remove_field(cond, field)` method: delete `field` from every "
        "document matching `cond` that has it; return the list of updated doc_ids",
        """db = TinyDB(storage=MemoryStorage); t = db.table('x')
    t.insert_multiple([{'k': 'a', 'tmp': 1}, {'k': 'b', 'tmp': 2}])
    q = Query()
    t.remove_field(q.k == 'a', 'tmp')
    assert 'tmp' not in t.get(q.k == 'a') and t.get(q.k == 'b')['tmp'] == 2
    assert 'remove_field' in t.journal """,
    ),
    (
        "replace",
        "add a `Table.replace(cond, document)` method: fully replace every document "
        "matching `cond` with `document` (same doc_ids kept); return the list of "
        "replaced doc_ids",
        """db = TinyDB(storage=MemoryStorage); t = db.table('x')
    ids = t.insert_multiple([{'k': 'a', 'n': 1}, {'k': 'b'}])
    q = Query()
    out = t.replace(q.k == 'a', {'k': 'a2'})
    assert out == [ids[0]]
    d = t.get(doc_id=ids[0])
    assert d == {'k': 'a2'}
    assert 'replace' in t.journal """,
    ),
]


def build_tasks() -> list[dict]:
    tasks = []
    for index, (name, spec, body) in enumerate(_SPECS):
        prompt = (
            f"In the `tinydb` library, {spec}. Keep the existing test suite "
            "passing (`python -m pytest tests/`); do not edit existing tests."
        )
        if index == 0:
            prompt += CONVENTION

        test = _TEST_HEADER + f"def test_{name}():\n    " + body + "\n"
        tasks.append({"id": f"task-{name}", "prompt": prompt, "test": test})

    return tasks


TASKS = build_tasks()
