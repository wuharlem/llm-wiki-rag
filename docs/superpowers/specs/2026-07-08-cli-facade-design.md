# CLI Facade — Design

**Date:** 2026-07-08
**Status:** Approved pending user review
**Goal:** Decouple every out-of-repo caller (vault PROCESS docs, scheduled cloud tasks) from the repo's internal module layout by giving them one stable shell surface: `python -m scripts.cli <command>`.

## Motivation

The 2026-07-08 pipeline-phase restructure (PR #29) required sweeping ~25 script references across the vault PROCESS docs and broke the `ai-safety-daily-digest` scheduled task, because those callers embed internal module paths. Interactive callers were untouched — the MCP tool names are a stable contract. Shell callers deserve the same: a call surface whose names never change when internals move.

## Non-goals

- No `wiki` console entry point. `tool.uv package = false` stays; flipping it would install a package named `scripts` into the venv (collision-prone) or force another rename. Rejected as Approach B during design.
- No new MCP tools. MCP remains the interactive surface, unchanged.
- No behavior, flag, or output changes to any existing module. The facade is additive; direct `python -m scripts.build.index` invocations keep working.
- No central flag definitions. Each module keeps owning its argparse (thin forwarding was chosen explicitly over a central parser).

## 1. The facade: `scripts/cli.py`

One module, invoked as `uv run python -m scripts.cli <command> [args...]` from the repo root (or with `uv run --directory <repo>` from anywhere). It contains a single command table — the public contract:

| Command | Forwards to | Notes |
|---|---|---|
| `build` | `scripts.build.index` | flags pass through (`--no-detail-md`, `--md-only`, `--limit`, `--vault`) |
| `mirror` | `scripts.build.wiki_mirror` | |
| `embed` | `scripts.build.embeddings` | needs `uv run --extra semantic` (wrapper-level, not facade's concern) |
| `query` | `scripts.serve.query_cli` | |
| `serve` | `scripts.serve.mcp_server` | |
| `fetch` | `scripts.ingest.fetch` | |
| `stage` | `scripts.ingest.stage_candidate` | the daily-digest caller |
| `dedup` | `scripts.ingest.dedup_report` | |
| `cleanup` | `scripts.maintenance.cleanup_metadata` | `--apply` passes through |
| `vocab-sync` | `scripts.maintenance.check_vocab_sync` | exit 1 = drift, exit 2 = parse failure (propagated) |
| `notion-regen` | `scripts.maintenance.regenerate_notion_sources` | |

**Forwarding mechanism:** rewrite `sys.argv` to `[<target module>, *rest]` and call `runpy.run_module(target, run_name="__main__")`. Zero changes to target modules; their argparse, `--help`, prints, and exit codes (including `SystemExit`) propagate untouched.

**Facade-owned behavior (all of it):**
- `python -m scripts.cli` bare, `--help`, or `-h` → print the command table with a one-line description per command, exit 0.
- Unknown command → print "unknown command: X" plus the table to stderr, exit 2.
- Everything else — including a command's own `--help` — is the target module's.

Each table entry carries a one-line description string (used only by the facade's help output).

## 2. The contract shift (CLAUDE.md §11)

A new cross-folder contract section is added to CLAUDE.md:

- The facade command names in §1's table are **frozen**: out-of-repo callers (vault PROCESS docs, scheduled tasks, anything not in this git repo) reference only `python -m scripts.cli <command>` — never phase-module paths.
- Moving/renaming internal modules only requires updating the facade's table — no doc sweep.
- Renaming or removing a **facade command** is the breaking change: it requires the same-session vault-doc sweep, exactly like renaming an MCP tool (§4).
- MCP (§4) remains the interactive contract; the facade is the shell contract. Same philosophy, two transports.

## 3. Reference updates (same working session)

- **Vault `PROCESS_HEALTH_CHECK.md`:** the ~6 shell commands become the facade form, e.g. `uv run --directory ~/Documents/Claude/Projects/AI\ Safety python -m scripts.cli vocab-sync`; the embeddings line keeps `--extra semantic` on the `uv run` wrapper. `PROCESS_NEW_FILE.md`: prose references to runnable commands likewise. `PROCESS_QUERY.md`: untouched (MCP-only, verified twice now).
- **Daily-digest scheduled task:** the user updates its instructions in the claude.ai UI; we supply the exact replacement line (`python3 -m scripts.cli stage URL [--title T] [--note N]` from the repo checkout root, or the `uv run --directory` form).
- **Repo `README.md` + `scripts/README.md`:** runnable quickstart commands switch to facade form so there is one documented way to run things; phase-module paths remain in prose that describes code layout.
- **`scripts/ingest/stage_candidate.py` usage docstring** (and any module docstring that advertises its own invocation): point at the facade form.

## 4. Tests

`tests/meta/test_cli_facade.py`:
1. **Table integrity:** every command's target module resolves via `importlib.util.find_spec`.
2. **Forwarding:** running the facade with `["vocab-sync", "--help"]` (via `runpy`/subprocess) exits 0 and emits the target's help text (proves argv rewrite + propagation).
3. **Unknown command:** exits 2, lists available commands.
4. **Bare/`--help`:** exits 0, lists every table command.

Guard test (marked `needs_vault`, auto-skips without the vault): the three vault PROCESS docs contain no `python -m scripts.(build|serve|ingest|maintenance)` or `python3 -m scripts.(build|serve|ingest|maintenance)` strings — the decoupling cannot silently erode. (`scripts.cli` and `scripts/wiki_lib/...` prose references remain legal.)

## Decisions log

| Decision | Choice | Alternatives rejected |
|---|---|---|
| Surface | `python -m scripts.cli` facade | `wiki` console script (packaging flip); everything-through-MCP (cloud tasks can't reach local MCP) |
| Forwarding | `runpy.run_module` after argv rewrite, thin | central argparse defining all flags (two places per flag) |
| Coverage | all 11 runnable modules | only the 6 PROCESS-doc commands (a line each; one documented way wins) |
| Contract | facade names frozen via CLAUDE.md §11 + vault guard test | convention only (eroded silently before) |
