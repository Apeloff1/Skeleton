"""Mandatory provider validation retains bounded caches without dropping checks."""
import importlib.util
from pathlib import Path


def validator():
    path=Path(__file__).parents[1]/'scripts/check_provider_bootstrap.py'
    spec=importlib.util.spec_from_file_location('dragon_provider_validator',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_evicted_module_is_reparsed_and_provider_imports_remain_visible(tmp_path):
    module=validator()
    first=tmp_path/'first.py';first.write_text('import openai\nimport httpx\n')
    assert module._imported_modules(first)==['openai','httpx']
    for i in range(256):
        path=tmp_path/f'module_{i}.py';path.write_text('import math\n')
        assert module._python_tree(path) is not None
        module._python_source(path)
    assert module._cached_python_tree.cache_info().currsize==128
    assert module._cached_source.cache_info().currsize==128
    assert module._python_tree(first) is not None
    assert module._imported_modules(first)==['openai','httpx']


def test_changed_source_invalidates_import_summary(tmp_path):
    module=validator();path=tmp_path/'provider.py'
    path.write_text('import math\n')
    assert module._imported_modules(path)==['math']
    path.write_text('import openai\nimport httpx\n')
    assert module._imported_modules(path)==['openai','httpx']
