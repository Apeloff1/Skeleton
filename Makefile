.PHONY: install dev app app-preload app-setup app-install windows-installer app-check app-status app-down precompile test test-feature smoke verify quality ci lint clean

install:
	pip install -r requirements.txt

dev:
	pip install -r requirements-dev.txt

app:
	python -m skeleton app up

app-preload:
	python -m skeleton app preload

app-setup:
	python -m skeleton app setup

app-install:
	python -m skeleton app install

windows-installer:
	pwsh ./scripts/windows/build_installer.ps1

app-check:
	python -m skeleton app check

# Read-only precompilation contract pass; not a compiled/runtime release verdict.
# Keep execution local to avoid unnecessary GitHub Actions runs.
precompile:
	python scripts/check_architecture_map.py
	python scripts/check_ai_app_construction.py
	python scripts/check_capability_interfaces.py
	python scripts/check_provider_bootstrap.py
	python scripts/check_state_topology.py
	python scripts/check_ai_file_tree.py
	python scripts/check_ai_file_tree_ownership.py
	python scripts/check_enterprise_ai_superiority.py --json
	python scripts/check_enterprise_ai_implementation_notes.py --json
	python scripts/check_app_assembly.py
	python scripts/check_toolchain_contract.py
	python -m skeleton app check

app-status:
	python -m skeleton app status

app-down:
	python -m skeleton app down

test:
	python -m pytest skeleton/testing -v --tb=short

test-feature:
	python scripts/run_feature_unit_tests.py --feature "$(FEATURE)"

smoke:
	bash scripts/cockpit-smoke.sh

verify:
	bash scripts/verify-forge.sh

quality:
	bash scripts/quality-gates.sh

ci:
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
