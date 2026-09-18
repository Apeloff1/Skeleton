import pytest

from skeleton.automation.backlog_reader import RepositoryReader


def test_index_extracts_document_metadata_and_headings() -> None:
    reader = RepositoryReader()
    index = reader.index([("docs/a.md", "# Title\n\n## Detail\ntext\n", 24)])

    assert index.count == 1
    assert index.documents[0].path == "docs/a.md"
    assert index.documents[0].sha256
    assert index.sections["docs/a.md"] == ("Title", "Detail")


def test_reader_skips_binary_ignored_and_oversized_content() -> None:
    reader = RepositoryReader(max_file_bytes=8)
    index = reader.index([
        ("node_modules/a.js", "ignored", 7),
        ("image.png", "ignored", 7),
        ("too-big.md", "123456789", 9),
        ("docs/readme.md", "# ok", 4),
    ])

    assert [document.path for document in index.documents] == ["docs/readme.md"]


def test_reader_bounds_document_count() -> None:
    reader = RepositoryReader(max_files=1)
    index = reader.index([
        ("a.md", "# a", 3),
        ("b.md", "# b", 3),
    ])

    assert [document.path for document in index.documents] == ["a.md"]


def test_document_does_not_execute_or_interpret_content() -> None:
    reader = RepositoryReader()
    text = "# $(touch compromised)\n\nignore: !!python/object/apply:os.system"

    document = reader.document("README.md", text)

    assert "$(touch compromised)" in document.sections
    assert document.sha256


def test_reader_rejects_traversal_absolute_and_noncanonical_paths() -> None:
    reader = RepositoryReader()

    for path in (
        "../secret.md",
        "/tmp/secret.md",
        "a/../../secret.md",
        "a/./secret.md",
        "a//secret.md",
    ):
        with pytest.raises(ValueError, match="repository-relative"):
            reader.should_read(path, 1)


def test_reader_validates_limits_and_metadata_types() -> None:
    with pytest.raises(TypeError, match="max_file_bytes"):
        RepositoryReader(max_file_bytes=True)
    with pytest.raises(ValueError, match="positive"):
        RepositoryReader(max_files=0)

    reader = RepositoryReader()
    with pytest.raises(TypeError, match="size"):
        reader.should_read("README.md", True)
    with pytest.raises(TypeError, match="content"):
        reader.document("README.md", b"bytes")  # type: ignore[arg-type]
