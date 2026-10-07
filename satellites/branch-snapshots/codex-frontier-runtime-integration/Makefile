.PHONY: install dev test smoke verify ci lint clean

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

ci:
	bash scripts/ci.sh

lint:
	python -m compileall skeleton -q
	python -c "import skeleton; from skeleton.genesis import Genesis; Genesis(seed=42).boot()"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
