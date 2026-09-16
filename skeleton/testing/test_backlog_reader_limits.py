import pytest

from skeleton.automation.backlog_reader import RepositoryReader


def test_declared_size_cannot_bypass_actual_content_limit() -> None:
    reader = RepositoryReader(max_file_bytes=4)

    with pytest.raises(ValueError, match="size limit"):
        reader.index([("README.md", "12345", 4)])


def test_nul_paths_fail_closed() -> None:
    reader = RepositoryReader()

    with pytest.raises(ValueError, match="repository-relative"):
        reader.should_read("docs/bad\x00name.md", 1)
