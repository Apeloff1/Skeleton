from skeleton.automation.backlog_index import RepositoryIndexBuilder
from skeleton.automation.backlog_reader import RepositoryReader


def test_requirements_options_and_direct_urls_are_not_misclassified_as_packages() -> None:
    reader = RepositoryReader()
    content = (
        "-r shared.txt\n"
        "--extra-index-url https://example.invalid/simple\n"
        "git+https://example.invalid/repo.git\n"
        "https://example.invalid/archive.whl\n"
        "fastapi>=1\n"
    )
    document = reader.document("requirements.txt", content)

    index = RepositoryIndexBuilder().build([(document, content)])

    assert [item.name for item in index.dependencies] == ["fastapi"]
