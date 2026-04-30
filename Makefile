# Targets:
#   install     - sync deps with the test extra
#   fmt         - apply formatting in-place (local convenience)
#   fmt-check   - verify formatting, fail if anything would change (CI)
#   lint        - run ruff check
#   test        - run pytest
#   check       - run all three CI checks (fmt-check, lint, test)
#   help        - print this list

.PHONY: install fmt fmt-check lint test check help
.DEFAULT_GOAL := help

UV ?= uv
RUFF := $(UV) run --extra test ruff
PYTEST := $(UV) run --extra test pytest

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

check: fmt-check lint test

help:
	@grep -E '^#   [a-z]' Makefile | sed 's/^#   //'
