.PHONY: install dev test smoke verify quality ci lint clean repo-intel repo-intel-check repo-intel-impact repo-intel-doctor

install:
	pip install -r requirements.txt

dev:
	pip install -r requirements-dev.txt

test:
	python -m pytest skeleton/testing -v --tb=short || python -m unittest discover skeleton/testing -v

smoke:
	bash scripts/cockpit-smoke.sh

verify:
	bash scripts/verify-forge.sh

quality:
	bash scripts/quality-gates.sh

repo-intel:
	python scripts/repo_intel_sota.py check
	python scripts/repo_intel_sota.py snapshot --out .cache/repo-intel

repo-intel-check:
	python scripts/repo_intel_sota.py gate --base "$${REPO_INTEL_BASE:-origin/main}"
	python scripts/repo_intel_sota.py snapshot --base "$${REPO_INTEL_BASE:-origin/main}" --out .cache/repo-intel

repo-intel-impact:
	python scripts/repo_intel_sota.py impact --base "$${REPO_INTEL_BASE:-origin/main}" --out .cache/repo-intel

repo-intel-doctor:
	python scripts/repo_intel_sota.py doctor --out .cache/repo-intel

ci:
	python scripts/repo_intel_sota.py check
	bash scripts/ci.sh

lint:
	python -m compileall skeleton -q
	python -c "import skeleton; from skeleton.genesis import Genesis; Genesis(seed=42).boot()"

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d \( -name ".pytest_cache" -o -name ".mypy_cache" -o -name ".ruff_cache" \) -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type f \( -name "*.pyc" -o -name "*.pyo" -o -name ".coverage.*" \) -delete 2>/dev/null || true
	rm -rf build dist htmlcov coverage_html .coverage .cache .tox .nox
