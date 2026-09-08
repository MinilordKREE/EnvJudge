# aea developer entrypoints. Every target runs through uv so the committed lockfile is honoured.
UV ?= uv
PYTHON_VERSION ?= 3.12

.PHONY: setup lock lint format typecheck test test-integration check clean

setup:  ## install uv if missing, sync the locked environment, install hooks
	@command -v $(UV) >/dev/null 2>&1 || python3 -m pip install --user uv
	@$(UV) python find $(PYTHON_VERSION) >/dev/null 2>&1 || $(UV) python install $(PYTHON_VERSION)
	$(UV) sync --locked
	$(UV) run pre-commit install

setup-alfworld:  ## ALFWorld/TextWorld extra (integration tests and experiments). The setup.py builds of
	## textworld / visdom / alfworld need an old setuptools: pyproject's [tool.uv.extra-build-dependencies]
	## and build-constraint-dependencies supply setuptools<81 to their isolated builds.
	$(UV) sync --locked --extra alfworld
	@echo "set ALFWORLD_DATA to the game data directory (e.g. export ALFWORLD_DATA=~/eh_alfworld_data)"

lock:  ## regenerate uv.lock after editing pyproject dependencies
	$(UV) lock

lint:  ## ruff lint + format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format:  ## apply ruff formatting and safe fixes
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

typecheck:  ## mypy --strict (configured in pyproject)
	$(UV) run mypy

test:  ## offline unit tests (integration tests deselected by default)
	$(UV) run pytest

test-integration:  ## LLM-free integration tests; need the alfworld extra and ALFWORLD_DATA
	$(UV) run pytest -m integration

check: lint typecheck test

clean:
	rm -rf .ruff_cache .mypy_cache .pytest_cache dist build
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
