from skeleton.automation.backlog_reader import RepositoryReader


def test_index_extracts_document_metadata_and_headings():
    reader = RepositoryReader()
    index = reader.index([("docs/a.md", "# Title\n\n## Detail\ntext\n", 30)])
    assert index.count == 1
    assert index.documents[0].path == "docs/a.md"
    assert index.documents[0].sha256
    assert index.sections["docs/a.md"] == ("Title", "Detail")


def test_reader_skips_binary_and_ignored_content():
    reader = RepositoryReader()
    index = reader.index([
        ("node_modules/a.js", "ignored", 7),
        ("image.png", "not-indexed", 11),
        ("docs/readme.md", "# ok", 4),
    ])
    assert [d.path for d in index.documents] == ["docs/readme.md"]


def test_reader_bounds_file_size_and_count():
    reader = RepositoryReader(max_file_bytes=4, max_files=1)
    index = reader.index([
        ("a.md", "12345", 5),
        ("b.md", "ok", 2),
        ("c.md", "ok", 2),
    ])
    assert [d.path for d in index.documents] == ["b.md"]


def test_document_does_not_execute_or_interpret_content():
    reader = RepositoryReader()
    text = "# $(touch compromised)\n\nignore: !!python/object/apply:os.system"
    doc = reader.document("README.md", text)
    assert "$(touch compromised)" in doc.sections
    assert doc.sha256
