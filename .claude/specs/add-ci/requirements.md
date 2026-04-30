# Requirements — `add-ci`

## Introduction

Add a continuous-integration workflow that runs **format**, **lint**, and **test** checks on every pull request (and on `main` push) so that broken or unstyled code cannot be merged. Tooling commands are wrapped in a top-level `Makefile` so the same checks run identically on a developer laptop and in GitHub Actions — eliminating "works on my machine" drift.

### Scope-bounding context (derived from the codebase)

- Project is a Python ≥3.10 workspace managed by **`uv`** (`uv.lock` is checked in, `pyproject.toml` declares optional extras `test`, `semantic`, `indexing`, `rerank`, `all`).
- Tests live in `tests/` and are invoked via `pytest`. Three custom markers exist: `slow`, `needs_index`, `needs_embeddings`. Tests that depend on built artifacts (`01_data/index/`) currently *skip* when artifacts are missing — which means CI can run the fast subset without rebuilding the index.
- No formatter or linter is currently configured. We will introduce **Ruff** (single tool for both `ruff format` and `ruff check`) because it is fast, zero-config-friendly, and avoids running two tools (Black + Flake8). Type-checking (mypy/pyright) is **out of scope** per user request.
- No `Makefile` and no `.github/` exist yet — this spec creates both from scratch.

## Alignment with Product Vision

This is internal tooling for a single-maintainer research repo. The vision served is **prevent regressions in the RAG pipeline and MCP server without slowing the maintainer down**: CI must be fast (target < 3 min on PRs), require zero local setup beyond `uv sync`, and not block merges on tests that legitimately need the prebuilt index.

## Requirements

### Requirement 1 — CI runs automatically on PRs and `main` pushes

**User Story:** As the repo maintainer, I want CI to run automatically on every pull request and on every push to `main`, so that broken code cannot reach `main` undetected.

#### Acceptance Criteria

1. WHEN a pull request is opened or updated against `main` THEN the CI workflow SHALL run all three jobs (fmt, lint, test).
2. WHEN a commit is pushed directly to `main` THEN the CI workflow SHALL run all three jobs.
3. WHEN none of `*.py`, `pyproject.toml`, `uv.lock`, `Makefile`, or `.github/workflows/**` change in a PR THEN the workflow MAY be skipped via path filters (optimization, not required for v1).
4. IF a CI job fails THEN GitHub SHALL mark the PR check as failed and block "Merge" if branch protection is enabled.

### Requirement 2 — Format check (non-mutating in CI)

**User Story:** As the maintainer, I want CI to verify that all Python code is already formatted, so that the diff stays consistent and reviewers never argue about whitespace.

#### Acceptance Criteria

1. WHEN the format job runs THEN it SHALL execute `ruff format --check` against the repo (or `make fmt-check`).
2. IF any file would be reformatted THEN the job SHALL exit non-zero and print the diff (or list of files).
3. The format job SHALL NOT modify files in CI — only verify.
4. A separate local target (`make fmt`) SHALL exist that *applies* formatting, so the maintainer can fix violations with one command.

### Requirement 3 — Lint check

**User Story:** As the maintainer, I want CI to run a linter so that obvious bugs (unused imports, undefined names, dead code) are caught before merge.

#### Acceptance Criteria

1. WHEN the lint job runs THEN it SHALL execute `ruff check` against the repo (or `make lint`).
2. IF any lint violation is reported THEN the job SHALL exit non-zero with the violation list.
3. Ruff configuration SHALL live in `pyproject.toml` under `[tool.ruff]` so local and CI runs agree.
4. The initial rule set SHALL be Ruff's default (`E`, `F`, `W`) plus `I` (isort) — broad enough to catch real bugs, narrow enough that the existing codebase passes without a large cleanup PR. Adding more rules is an explicit follow-up, not part of this spec.
5. IF the existing codebase fails lint with the chosen rule set THEN the spec SHALL include a one-time cleanup task before the workflow is enabled as required (otherwise the first PR that adopts CI would be blocked by inherited violations).

### Requirement 4 — Test suite

**User Story:** As the maintainer, I want CI to run the pytest suite so that regressions in retrieval/build/MCP code are caught automatically.

#### Acceptance Criteria

1. WHEN the test job runs THEN it SHALL execute `pytest` (or `make test`) with the project's `test` extra installed.
2. Tests marked `needs_index` or `needs_embeddings` SHALL skip cleanly in CI (no built artifacts are present in the runner) — this is **already** the conftest behavior; the requirement is to verify it holds.
3. Tests marked `slow` SHALL run by default in CI v1 (the existing `slow` tests are still under a few seconds; revisit if total runtime exceeds the 3 min target).
4. IF any non-skipped test fails THEN the job SHALL exit non-zero and the failure output SHALL be visible in the GitHub Actions log.
5. The test job SHALL run against Python 3.10 only in v1 (matching `requires-python = ">=3.10"` floor). Multi-version matrix is an explicit non-goal.

### Requirement 5 — Makefile as the single source of truth

**User Story:** As the maintainer, I want one place that defines what "fmt", "lint", and "test" mean, so that local dev and CI cannot drift.

#### Acceptance Criteria

1. The repo SHALL contain a top-level `Makefile` with at minimum these targets: `fmt`, `fmt-check`, `lint`, `test`, `check` (runs all three CI checks), `install` (runs `uv sync --extra test`).
2. The CI workflow SHALL invoke targets via `make <target>` rather than reimplementing the commands inline.
3. Each target SHALL be a single, readable line (or a short block) — no hidden complexity.
4. `make help` (or running `make` with no target) SHOULD print the available targets and a one-line description of each.

### Requirement 6 — Dependency install is fast and reproducible

**User Story:** As the maintainer, I want CI to use the same dependency resolver as local dev, so that lock-file drift is impossible and CI install completes in seconds.

#### Acceptance Criteria

1. The CI workflow SHALL use **`uv`** (via `astral-sh/setup-uv@v3` or the `pip install uv` shortcut) — not raw `pip install -e .`.
2. The CI workflow SHALL install dependencies via `uv sync --extra test` so the same resolved versions from `uv.lock` are used.
3. The workflow SHALL cache `uv`'s download cache keyed by `uv.lock` hash, so unchanged-lock runs install in < 10 s.
4. IF `uv.lock` is out of sync with `pyproject.toml` THEN `uv sync` SHALL fail in CI (no implicit relock).

### Requirement 7 — Workflow file location and naming

**User Story:** As the maintainer, I want the workflow files in conventional GitHub-recognized paths, so that GitHub picks them up automatically and other tools (status badges, branch protection) can reference them.

#### Acceptance Criteria

1. The workflow SHALL be at `.github/workflows/ci.yml`.
2. The workflow's `name:` SHALL be `CI` so it appears as "CI" in the PR status checks list.
3. Each job SHALL have a stable, human-readable name (`fmt`, `lint`, `test`) suitable for adding to GitHub branch-protection required-checks.

## Non-Goals (explicit, to keep scope tight)

- Multi-Python-version test matrix (3.11, 3.12, 3.13).
- Type checking (mypy / pyright).
- Coverage reporting / Codecov upload.
- Building or publishing artifacts (no wheels, no Docker images).
- Running tests that require the prebuilt index — those continue to skip in CI.
- Pre-commit hook setup. (Could be a follow-up; not required for the CI workflow itself.)
- Auto-formatting commits pushed back from CI.
- Caching of pytest/ruff outputs beyond the dependency cache.

## Open Questions for the User

These are decisions I made on your behalf using sensible defaults; flag any you want changed before we move to design:

1. **Ruff over Black+Flake8.** Picked Ruff because it does both jobs in one tool. OK?
2. **Single Python version (3.10).** No matrix in v1. OK?
3. **Lint rule set = `E,F,W,I`.** Ruff defaults plus isort. If the current codebase has violations under this set, we'll fix them in a one-time cleanup task in this same spec. OK?
4. **`needs_index` / `needs_embeddings` tests skip in CI.** This is already the conftest behavior; we're not changing it. OK?
5. **Workflow trigger = `pull_request` + `push: main` only.** No scheduled runs, no manual `workflow_dispatch` for v1. OK?
