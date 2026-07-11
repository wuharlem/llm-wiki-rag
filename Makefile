# Targets:
#   install     - sync deps with the test extra
#   fmt         - apply formatting in-place (local convenience)
#   fmt-check   - verify formatting, fail if anything would change (CI)
#   lint        - run ruff check
#   test        - run pytest
#   test-cov    - run pytest with the coverage ratchet (fails under COV_FLOOR)
#   check       - run all three CI checks (fmt-check, lint, test)
#   help        - print this list

.PHONY: install fmt fmt-check lint test test-cov check help
.DEFAULT_GOAL := help

UV ?= uv
RUFF := $(UV) run --extra test ruff
PYTEST := $(UV) run --extra test pytest

# Coverage ratchet floor (CI enforces via test-cov). RULES: only moves UP,
# and stays a couple of points below measured CI coverage — it exists to
# catch regressions, not to be a target. Exemptions: see .coveragerc.
COV_FLOOR := 72

install:
	$(UV) sync --extra test

fmt:
	$(RUFF) format scripts/ tests/
	$(RUFF) check --fix --select I scripts/ tests/

fmt-check:
	$(RUFF) format --check scripts/ tests/

lint:
	$(RUFF) check scripts/ tests/

test:
	$(PYTEST)

test-cov:
	$(UV) run --extra test --with pytest-cov pytest --cov=scripts --cov-config=.coveragerc --cov-report=term --cov-fail-under=$(COV_FLOOR)

check: fmt-check lint test

help:
	@grep -E '^#   [a-z]' Makefile | sed 's/^#   //'
