from skeleton.automation.backlog_index import RepositoryIndexBuilder
from skeleton.automation.backlog_reader import RepositoryReader


def test_index_builder_maps_symbols_dependencies_workflows_and_tests():
    reader = RepositoryReader()
    source = reader.document("src/app.py", "class App:\n    def run(self):\n        return True\n")
    requirements = reader.document("requirements.txt", "fastapi>=1\npytest==8\n")
    workflow = reader.document(".github/workflows/check.yml", "name: check\n")
    test = reader.document("tests/test_app.py", "def test_app():\n    assert True\n")
    index = RepositoryIndexBuilder().build([
        (source, "class App:\n    def run(self):\n        return True\n"),
        (requirements, "fastapi>=1\npytest==8\n"),
        (workflow, "name: check\n"),
        (test, "def test_app():\n    assert True\n"),
    ])
    assert {symbol.name for symbol in index.symbols} == {"App", "run"}
    assert [dependency.name for dependency in index.dependencies] == ["fastapi", "pytest"]
    assert index.workflows == (".github/workflows/check.yml",)
    assert index.tests == ("tests/test_app.py",)


def test_package_json_only_indexes_dependency_sections():
    reader = RepositoryReader()
    package = reader.document(
        "package.json",
        '{"name":"demo","version":"1","dependencies":{"react":"^1"},'
        '"devDependencies":{"vitest":"^2"},"scripts":{"build":"evil-not-a-dependency"}}',
    )
    index = RepositoryIndexBuilder().build([(package, package.path and '{"name":"demo","version":"1","dependencies":{"react":"^1"},"devDependencies":{"vitest":"^2"},"scripts":{"build":"evil-not-a-dependency"}}')])
    assert [(item.name, item.source) for item in index.dependencies] == [
        ("react", "package-json:dependencies"),
        ("vitest", "package-json:devDependencies"),
    ]


def test_index_order_is_deterministic():
    reader = RepositoryReader()
    first = reader.document("z.py", "def z():\n    pass\n")
    second = reader.document("a.py", "def a():\n    pass\n")
    index = RepositoryIndexBuilder().build([(first, "def z():\n    pass\n"), (second, "def a():\n    pass\n")])
    assert [doc.path for doc in index.files] == ["a.py", "z.py"]
    assert [symbol.name for symbol in index.symbols] == ["a", "z"]


def test_reader_rejects_traversal_and_absolute_paths():
    reader = RepositoryReader()
    for path in ("../secret.md", "/tmp/secret.md", "a/../../secret.md"):
        try:
            reader.should_read(path, 1)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe path accepted")


def test_reader_matches_ignored_filename_patterns():
    reader = RepositoryReader()
    index = reader.index([
        ("cache/data.pyc", "ignored", 7),
        ("archive/data.zip", "ignored", 7),
        ("docs/guide.md", "# ok", 5),
    ])
    assert [doc.path for doc in index.documents] == ["docs/guide.md"]
