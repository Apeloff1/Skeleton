"""The historical accounting enum exception must not suppress credentials."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '411d0f1ded21fc7b5629e0073df2dbd85b6b2db9'
PATH = 'frontend/src/features/Jeeves/RuntimeFoundationDetails.tsx'
LINE_DIGEST = '93c15dcdabd459f9740f99856fac48536a9ac7c48291265b005532099e35c3ad'


def _exception():
    config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
    matches = [allow for rule in config['rules'] if rule.get('id') == 'generic-api-key'
               for allow in rule.get('allowlists', [])
               if allow.get('description') == 'Historical public input-accounting enum check; exact commit, path and line only']
    assert len(matches) == 1
    return matches[0]


def test_exception_requires_exact_commit_path_and_line():
    allow = _exception()
    assert allow['condition'] == 'AND' and allow['regexTarget'] == 'line'
    assert allow['commits'] == [COMMIT]
    assert len(allow['paths']) == len(allow['regexes']) == 1
    path = re.compile(allow['paths'][0])
    assert path.fullmatch(PATH)
    assert not path.fullmatch('backend/' + PATH)
    assert not path.fullmatch(PATH + '.backup')
    assert not path.fullmatch(PATH.replace('RuntimeFoundationDetails', 'RuntimeFoundationDetail'))


def test_historical_enum_only_and_appended_credentials_are_not_exempted():
    result = subprocess.run(['git', 'show', f'{COMMIT}:{PATH}'], cwd=ROOT, text=True,
                            capture_output=True, timeout=15, check=False)
    if result.returncode:
        pytest.skip('Historical commit is absent from this checkout; full-history scan is required for this case')
    source = result.stdout
    line = source.splitlines()[46]
    assert hashlib.sha256(line.strip().encode()).hexdigest() == LINE_DIGEST
    literals = re.findall(r"(['\"])([^'\"]*)\1", line)
    assert len(literals) == 7 and all(re.fullmatch(r'[a-z][a-z0-9_]*', v) for _, v in literals)
    matcher = re.compile(_exception()['regexes'][0])
    assert matcher.fullmatch(line)
    # Altering the historical line, including by adding a new assignment,
    # must invalidate the exception; an opaque sentinel is not a credential.
    assert not matcher.fullmatch(line + '; api_key = "' + 'A' * 32 + '"')
    assert not matcher.fullmatch(line.replace('accounting.exact', 'accounting.other', 1))
    assert '0000000000000000000000000000000000000000' not in _exception()['commits']
