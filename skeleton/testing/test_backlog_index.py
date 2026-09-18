from skeleton.automation.backlog_index import RepositoryIndexBuilder
from skeleton.automation.backlog_reader import RepositoryReader


def test_index_builder_maps_symbols_dependencies_workflows_tests_and_imports() -> None:
    reader = RepositoryReader()
    source_text = (
        "from package.core import Service\n"
        "import os, sys\n\n"
        "class App:\n"
        "    def run(self):\n"
        "        return True\n"
    )
    source = reader.document("src/app.py", source_text)
    requirements_text = "fastapi>=1\npytest==8\n-r extra.txt\n"
    requirements = reader.document("requirements.txt", requirements_text)
    workflow_text = "name: check\n"
    workflow = reader.document(".github/workflows/check.yml", workflow_text)
    test_text = "def test_app():\n    assert True\n"
    test = reader.document("tests/test_app.py", test_text)

    index = RepositoryIndexBuilder().build([
        (source, source_text),
        (requirements, requirements_text),
        (workflow, workflow_text),
        (test, test_text),
    ])

    assert {(symbol.name, symbol.kind) for symbol in index.symbols} == {
        ("App", "class"),
        ("run", "function"),
        ("test_app", "function"),
    }
    assert [dependency.name for dependency in index.dependencies] == ["fastapi", "pytest"]
    assert index.workflows == (".github/workflows/check.yml",)
    assert index.tests == ("tests/test_app.py",)
    assert {(item.target, item.kind) for item in index.references} == {
        ("package.core", "import"),
        ("os", "import"),
        ("sys", "import"),
    }
    assert len(index.references_to("os")) == 1


def test_python_symbol_kind_uses_ast_not_name_substrings() -> None:
    reader = RepositoryReader()
    content = (
        "def classification():\n"
        "    return 1\n\n"
        "class Functional:\n"
        "    async def classifier(self):\n"
        "        return 2\n"
    )
    document = reader.document("classification.py", content)

    index = RepositoryIndexBuilder().build([(document, content)])

    assert [(item.name, item.kind) for item in index.symbols] == [
        ("Functional", "class"),
        ("classification", "function"),
        ("classifier", "function"),
    ]


def test_python_relative_imports_are_recorded_without_execution() -> None:
    reader = RepositoryReader()
    content = "from .core import Service\nfrom ..shared import helper\n"
    document = reader.document("pkg/module.py", content)

    index = RepositoryIndexBuilder().build([(document, content)])

    assert [item.target for item in index.references] == ["..shared", ".core"]


def test_invalid_python_is_fail_closed_for_static_records() -> None:
    reader = RepositoryReader()
    content = "import os\ndef broken(:\n    pass\n"
    document = reader.document("broken.py", content)

    index = RepositoryIndexBuilder().build([(document, content)])

    assert index.symbols == ()
    assert index.references == ()


def test_javascript_symbol_kind_does_not_depend_on_identifier_text() -> None:
    reader = RepositoryReader()
    content = "function classification() { return 1; }\nclass Runner {}\n"
    document = reader.document("src/app.js", content)

    index = RepositoryIndexBuilder().build([(document, content)])

    assert [(item.name, item.kind) for item in index.symbols] == [
        ("Runner", "class"),
        ("classification", "function"),
    ]


def test_package_json_only_indexes_dependency_sections() -> None:
    reader = RepositoryReader()
    content = (
        '{"name":"demo","version":"1","dependencies":{"react":"^1"},'
        '"devDependencies":{"vitest":"^2"},'
        '"scripts":{"build":"evil-not-a-dependency"}}'
    )
    package = reader.document("package.json", content)

    index = RepositoryIndexBuilder().build([(package, content)])

    assert [(item.name, item.source) for item in index.dependencies] == [
        ("react", "package-json:dependencies"),
        ("vitest", "package-json:devDependencies"),
    ]


def test_index_order_is_deterministic_and_deduplicates_references() -> None:
    reader = RepositoryReader()
    first_text = "import os\nimport os\n\ndef z():\n    pass\n"
    second_text = "def a():\n    pass\n"
    first = reader.document("z.py", first_text)
    second = reader.document("a.py", second_text)

    index = RepositoryIndexBuilder().build([(first, first_text), (second, second_text)])

    assert [document.path for document in index.files] == ["a.py", "z.py"]
    assert [symbol.name for symbol in index.symbols] == ["a", "z"]
    assert len(index.references) == 1
    assert index.references[0].target == "os"
