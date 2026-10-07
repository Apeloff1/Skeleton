from skeleton.automation.backlog_index import RepositoryIndexBuilder
from skeleton.automation.backlog_reader import RepositoryReader


def test_reader_and_index_are_deterministic_for_same_inputs() -> None:
    reader = RepositoryReader()
    files = [
        ("b.py", "import os\nclass B: pass\n", 25),
        ("a.md", "# A\n", 4),
    ]

    first = reader.index(files)
    second = reader.index(files)
    assert first == second

    docs = [(reader.document(path, content), content) for path, content, _ in files]
    assert RepositoryIndexBuilder().build(docs) == RepositoryIndexBuilder().build(docs)
