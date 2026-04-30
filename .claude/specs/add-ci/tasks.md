# Tasks — `add-ci`

Each task is scoped to 1–3 files and one testable outcome. Tasks are ordered so the repo stays green at every checkpoint: tooling and config land first, the codebase is brought into compliance, the Makefile is added, and only then does the workflow file go in (so the first PR with `ci.yml` is also the first PR that's already passing all checks).

## Phase A — Configuration

- [ ] **1. Add `[tool.ruff]` config to `pyproject.toml`**
  - File: `pyproject.toml`
  - Add three new sections per design doc Component 2: `[tool.ruff]` (with `line-length = 120`, `target-version = "py310"`, `extend-exclude`), `[tool.ruff.lint]` (`select = ["E","F","W","I"]`, `ignore = ["E501","E741"]`), `[tool.ruff.lint.per-file-ignores]` (`"scripts/*.py" = ["E402"]`), and `[tool.ruff.format]` (empty body, defaults).
  - Verify: `uv run --with ruff ruff check --show-settings | head -40` reports `line-length = 120` and the selected rule set.
  - Requirements: R3.3, R3.4

- [ ] **2. Add Ruff to the `test` extra in `pyproject.toml`**
  - File: `pyproject.toml`
  - Edit the `[project.optional-dependencies].test` array to add `"ruff>=0.5,<1.0"` next to `"pytest>=8"`.
  - Verify: `uv sync --extra test` succeeds and `uv run --extra test ruff --version` prints a 0.x version.
  - Requirements: R6.2 (locked tooling)

- [ ] **3. Re-lock dependencies**
  - File: `uv.lock`
  - Run `uv sync --extra test` (this updates `uv.lock` to include Ruff). Commit the lockfile delta.
  - Verify: `git diff uv.lock` shows ruff entries; `uv sync --extra test --frozen` succeeds.
  - Requirements: R6.2, R6.4

## Phase B — One-time codebase cleanup

These tasks bring the existing code into compliance with the rules from Phase A. Each is small and verifiable on its own.

- [ ] **4. Apply `ruff format` to `scripts/` and `tests/`**
  - Files: any of the 43 files under `scripts/` and `tests/` that need reformatting.
  - Run: `uv run --extra test ruff format scripts/ tests/`
  - Verify: `uv run --extra test ruff format --check scripts/ tests/` exits 0.
  - Verify: `uv run --extra test pytest -q` still passes (formatting must not change behavior).
  - Requirements: R2.1

- [ ] **5. Apply auto-fixable lint corrections**
  - Files: ~30 files across `scripts/` and `tests/` (touches: F401 unused imports, I001 import order, F541 empty f-strings, E401 multiple-imports-one-line).
  - Run: `uv run --extra test ruff check --fix scripts/ tests/`
  - Verify: `uv run --extra test pytest -q` still passes.
  - Verify: `uv run --extra test ruff check scripts/ tests/` reports only non-auto-fixable rules remaining (~30 errors expected: E701, E702, E402-not-in-scripts-dir, F841).
  - Requirements: R3.1

- [ ] **6. Manually fix residual `E701`/`E702` (multi-statement lines, ~27 cases)**
  - Files: split each affected line in `scripts/` and `tests/` so each statement is on its own line.
  - Verify: `uv run --extra test ruff check --select E701,E702 scripts/ tests/` reports zero errors.
  - Verify: `uv run --extra test pytest -q` still passes.
  - Requirements: R3.1

- [ ] **7. Manually fix residual `F841` (unused variables, 6 cases) and any remaining `E402` outside `scripts/`**
  - Files: ~6 files. For F841, either use the variable or delete the assignment (whichever matches intent — these are real bugs to look at, not mechanical fixes). For any E402 in `tests/` (not covered by the per-file-ignore), reorder imports.
  - Verify: `uv run --extra test ruff check scripts/ tests/` exits 0.
  - Verify: `uv run --extra test pytest -q` still passes.
  - Requirements: R3.1

## Phase C — Makefile

- [ ] **8. Create the top-level `Makefile`**
  - File: `Makefile` (new, repo root)
  - Implement targets per design doc Component 1: `install`, `fmt`, `fmt-check`, `lint`, `test`, `check`, `help`. Use `.PHONY` and `.DEFAULT_GOAL := help`. Variables `UV ?= uv`, `RUFF`, `PYTEST` exactly as in the design.
  - Verify: `make help` prints the target list.
  - Verify: `make fmt-check && make lint && make test` all exit 0.
  - Verify: `make check` exits 0 (covers all three).
  - Requirements: R5.1, R5.2, R5.3, R5.4

## Phase D — GitHub Actions workflow

- [ ] **9. Create `.github/workflows/ci.yml`**
  - File: `.github/workflows/ci.yml` (new; create `.github/` and `.github/workflows/` first)
  - Copy the workflow from design doc Component 3 verbatim. Three jobs (`fmt`, `lint`, `test`), each on `ubuntu-latest`, each with `actions/checkout@v4` + `astral-sh/setup-uv@v8` (with `enable-cache: true`; rely on the action's default `cache-dependency-glob` which already includes `uv.lock` and `pyproject.toml`) + `uv sync --extra test` + `make <target>`. Test job pins `python-version: "3.10"`. Top-level `concurrency` block cancels in-progress only on PRs.
  - Verify (local lint): `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` parses cleanly.
  - Verify (live): open a PR with these changes; all three checks (`fmt`, `lint`, `test`) report green in the PR's status.
  - Requirements: R1.1, R1.2, R1.4, R4.1, R4.2, R4.4, R4.5, R6.1, R6.2, R6.3, R7.1, R7.2, R7.3

## Phase E — Verification & wrap-up

- [ ] **10. End-to-end local dry run before opening the PR**
  - Files: none (verification only).
  - Run, in order, from a clean working tree: `make install`, `make check`. Both must exit 0.
  - Run a deliberate negative test: temporarily add `import os` (unused) to a script, run `make lint`, confirm it fails with F401, then revert.
  - Verify: `git status` is clean after revert.
  - Requirements: R3.1, R5.1

## User Action (post-implementation, not an agent task)

**Branch protection.** Once the workflow is merged, the maintainer should — in GitHub Settings → Branches → branch-protection rule for `main` — add `fmt`, `lint`, `test` to "Require status checks to pass before merging". This satisfies R1.4 (failed CI blocks merge); the workflow itself cannot configure this.

## Out of Scope (explicit, do not include in implementation)

- Multi-Python-version matrix
- Type checking (mypy/pyright)
- Coverage reporting
- Docker / wheel artifact builds
- Rebuilding `01_data/index/` in CI to enable `needs_index` tests
- Pre-commit hooks
- Path filters on the workflow trigger (R1.3 — deferred)

## Requirement → Task Coverage

| Requirement | Tasks |
|---|---|
| R1.1 (PR triggers) | 9 |
| R1.2 (push:main triggers) | 9 |
| R1.4 (failed PR is blocked) | 9 (CI side); branch protection (user action) |
| R2.1 (fmt-check uses --check) | 4, 8, 9 |
| R2.2 (fmt-check non-zero on drift) | 4, 8, 10 |
| R2.3 (CI does not mutate) | 8 (fmt-check ≠ fmt), 9 |
| R2.4 (local `make fmt` exists) | 8 |
| R3.1 (`ruff check` runs) | 5, 6, 7, 8, 9 |
| R3.2 (lint failure exits non-zero) | 8, 10 |
| R3.3 (config in pyproject.toml) | 1 |
| R3.4 (rule set E,F,W,I) | 1 |
| R3.5 (cleanup before enable) | 4, 5, 6, 7 |
| R4.1 (pytest runs) | 8, 9 |
| R4.2 (`needs_index`/`needs_embeddings` skip) | 9 (verified during live run) |
| R4.3 (`slow` runs by default) | 8 (`make test` calls bare `pytest`) |
| R4.4 (test failure → non-zero exit) | 8, 9 |
| R4.5 (Python 3.10 only) | 9 |
| R5.1 (Makefile targets) | 8 |
| R5.2 (CI invokes via make) | 9 |
| R5.3 (targets are simple) | 8 |
| R5.4 (`make help`) | 8 |
| R6.1 (uv-based install) | 9 |
| R6.2 (`uv sync --extra test`) | 2, 3, 9 |
| R6.3 (uv cache keyed on uv.lock) | 9 |
| R6.4 (lock drift fails CI) | 3, 9 |
| R7.1 (workflow path) | 9 |
| R7.2 (workflow name `CI`) | 9 |
| R7.3 (job names) | 9 |
