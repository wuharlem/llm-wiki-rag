# CLI Facade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give out-of-repo callers (vault PROCESS docs, scheduled tasks) one stable shell surface — `python -m scripts.cli <command>` — so internal module moves never again require doc sweeps.

**Architecture:** A single dispatch module `scripts/cli.py` holding a frozen command table; forwarding is `sys.argv` rewrite + `runpy.run_module(target, run_name="__main__")`, so target modules keep owning their argparse, flags, help, and exit codes with zero changes. A vault-guard test makes the decoupling contract enforceable.

**Tech Stack:** Python 3.10+ stdlib only (`runpy`, `sys`), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-07-08-cli-facade-design.md`

## Global Constraints

- The 11 command names are FROZEN on merge: `build, mirror, embed, query, serve, fetch, stage, dedup, cleanup, vocab-sync, notion-regen`. Exact target mapping in Task 1's table — deviations are spec violations.
- Zero changes to any target module's behavior, flags, or argparse (the `stage_candidate.py` docstring text update in Task 2 is the sole allowed edit, and it touches no code).
- Facade-owned behavior is ONLY: bare/`-h`/`--help` → command table to stdout, exit 0; unknown command → error + table to stderr, exit 2. Everything else propagates from the target.
- Old `python -m scripts.<phase>.<module>` invocations must keep working (facade is additive).
- Vault edits stay UNSTAGED in the vault's git repo (user reviews); never commit there. Only `PROCESS_HEALTH_CHECK.md`, `PROCESS_NEW_FILE.md` may be edited in the vault this time (no log.md entry — this change is repo-side; the PROCESS-doc command swap is cosmetic).
- CLAUDE.md is gitignored: edit fully, never commit.
- Suite baseline: 168 passed + 1 skipped. `make fmt && make lint` before each commit. Branch: `feat/cli-facade` (exists).

---

### Task 1: `scripts/cli.py` + facade tests

**Files:**
- Create: `scripts/cli.py`
- Test: `tests/meta/test_cli_facade.py`

**Interfaces:**
- Consumes: the 11 existing runnable modules (all verified to have `if __name__ == "__main__":` guards).
- Produces: `scripts.cli.COMMANDS: dict[str, tuple[str, str]]` (name → (target module, description)) and `scripts.cli.main(argv: list[str] | None = None) -> None` (raises `SystemExit`). Tasks 2–3 reference command names; the guard test added in Task 3 lives in this task's test file.

- [ ] **Step 1: Write the failing tests**

Create `tests/meta/test_cli_facade.py`:

```python
"""test_cli_facade — the scripts.cli command table is importable, forwards
argv to its targets, and rejects unknown commands.

The command names in scripts.cli.COMMANDS are a frozen contract
(CLAUDE.md §11): vault PROCESS docs and scheduled tasks call only these.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys

import pytest

from scripts import cli
from scripts.wiki_lib.locations import work_path

EXPECTED_COMMANDS = {
    "build", "mirror", "embed", "query", "serve", "fetch",
    "stage", "dedup", "cleanup", "vocab-sync", "notion-regen",
}


def test_command_table_is_exactly_the_frozen_contract():
    assert set(cli.COMMANDS) == EXPECTED_COMMANDS


def test_every_target_module_resolves():
    missing = {
        name: target
        for name, (target, _desc) in cli.COMMANDS.items()
        if importlib.util.find_spec(target) is None
    }
    assert not missing, f"facade targets that do not import: {missing}"


def test_bare_invocation_prints_table_and_exits_0(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for name in cli.COMMANDS:
        assert name in out, f"help table missing command {name!r}"


def test_unknown_command_exits_2_with_table(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["frobnicate"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "unknown command: frobnicate" in err
    assert "vocab-sync" in err


def test_forwarding_reaches_target_help():
    """`cli vocab-sync --help` must exit 0 with the TARGET's argparse help.

    Run in a subprocess: runpy re-executes the target under __main__, which
    would RuntimeWarning if the module is already imported in this process.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.cli", "vocab-sync", "--help"],
        capture_output=True,
        text=True,
        cwd=str(work_path()),
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "usage" in proc.stdout.lower()
    assert "check_vocab_sync" in proc.stdout or "vocab" in proc.stdout.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra test pytest tests/meta/test_cli_facade.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'scripts.cli'` (all 5 tests fail at import).

- [ ] **Step 3: Write `scripts/cli.py`**

```python
"""scripts.cli — the stable shell surface for out-of-repo callers.

Usage:
    uv run python -m scripts.cli <command> [args...]

The command names below are a FROZEN contract (CLAUDE.md §11): vault
PROCESS docs and scheduled tasks reference only these names. Internal
modules may move freely — update COMMANDS here and nothing else changes.

Forwarding is deliberately thin: argv is rewritten and the target module
is executed via runpy under __main__, so each target keeps owning its
argparse, flags, output, and exit codes.
"""

from __future__ import annotations

import runpy
import sys

# command -> (target module, one-line description for the help table)
COMMANDS: dict[str, tuple[str, str]] = {
    "build": ("scripts.build.index", "Build the chunked RAG index (chunks.jsonl, manifest.csv)"),
    "mirror": ("scripts.build.wiki_mirror", "Rebuild the Obsidian _index/ mirror from the manifest"),
    "embed": ("scripts.build.embeddings", "Embed chunks for hybrid retrieval (run with --extra semantic)"),
    "query": ("scripts.serve.query_cli", "Query the index from the shell (BM25 + dense + RRF)"),
    "serve": ("scripts.serve.mcp_server", "Run the wiki MCP server (stdio)"),
    "fetch": ("scripts.ingest.fetch", "Bulk-fetch URLs into the vault's Sources/_inbox/"),
    "stage": ("scripts.ingest.stage_candidate", "Stage one URL into _add_by_me/ (daily-digest entrypoint)"),
    "dedup": ("scripts.ingest.dedup_report", "Report duplicate sources by canonical URL + title"),
    "cleanup": ("scripts.maintenance.cleanup_metadata", "Blank suspect published/author frontmatter (--apply to write)"),
    "vocab-sync": ("scripts.maintenance.check_vocab_sync", "Lint the vault vocab table against wiki_schema.yml"),
    "notion-regen": ("scripts.maintenance.regenerate_notion_sources", "Regenerate 01_data/notion_sources.csv from vault state"),
}


def _print_table(stream) -> None:
    print("usage: python -m scripts.cli <command> [args...]", file=stream)
    print("commands:", file=stream)
    width = max(len(name) for name in COMMANDS)
    for name, (_target, desc) in COMMANDS.items():
        print(f"  {name:<{width}}  {desc}", file=stream)
    print("run a command with --help for its own flags", file=stream)


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] in ("-h", "--help"):
        _print_table(sys.stdout)
        raise SystemExit(0)
    command, rest = args[0], args[1:]
    entry = COMMANDS.get(command)
    if entry is None:
        print(f"unknown command: {command}", file=sys.stderr)
        _print_table(sys.stderr)
        raise SystemExit(2)
    target, _desc = entry
    sys.argv = [target, *rest]
    runpy.run_module(target, run_name="__main__")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra test pytest tests/meta/test_cli_facade.py -v`
Expected: 5 passed.

- [ ] **Step 5: Full suite + commit**

```bash
make fmt && make lint && make check
git add scripts/cli.py tests/meta/test_cli_facade.py
git commit -m "feat(cli): scripts.cli facade — stable shell surface for out-of-repo callers

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: `make check` = 173 passed + 1 skipped (168 baseline + 5 new).

---

### Task 2: Repo docs — CLAUDE.md §11, READMEs, stage_candidate docstring

**Files:**
- Modify: `CLAUDE.md` (gitignored — edit, do NOT commit), `README.md`, `scripts/README.md`, `scripts/ingest/stage_candidate.py` (docstring only)

**Interfaces:**
- Consumes: command names from Task 1's table.
- Produces: the §11 contract text Task 3's vault sweep cites.

- [ ] **Step 1: Append §11 to CLAUDE.md's "Cross-folder contracts" section (after §10)**

```markdown
### 11. Shell callers go through the `scripts.cli` facade (frozen command names)

Out-of-repo shell callers — the vault PROCESS docs and scheduled tasks (e.g.
`ai-safety-daily-digest`) — invoke pipeline code ONLY as
`uv run --directory <repo> python -m scripts.cli <command>`. The command
table lives in `scripts/cli.py::COMMANDS`:

`build, mirror, embed, query, serve, fetch, stage, dedup, cleanup,
vocab-sync, notion-regen`

- Moving/renaming an internal module = update `COMMANDS` in `scripts/cli.py`;
  no doc sweep.
- Renaming/removing a **facade command** = breaking change to the vault docs
  and scheduled tasks — same-session sweep required, exactly like renaming an
  MCP tool (§4). MCP is the interactive contract; the facade is the shell
  contract.
- Enforced by `tests/meta/test_cli_facade.py` (table integrity) and its
  `needs_vault` guard test (PROCESS docs contain no raw
  `python -m scripts.<phase>` commands).
```

- [ ] **Step 2: Switch runnable commands in both READMEs to facade form**

`grep -n "python -m scripts\." README.md scripts/README.md` and convert every RUNNABLE command line: `python -m scripts.build.index` → `python -m scripts.cli build`, `... scripts.build.embeddings` → `... scripts.cli embed` (keep `--extra all`/`--extra semantic` on the `uv run` wrapper), `... scripts.serve.query_cli "RLHF"` → `... scripts.cli query "RLHF"`, `... scripts.serve.mcp_server` → `... scripts.cli serve`, `... scripts.ingest.fetch [flags]` → `... scripts.cli fetch [flags]`, `... scripts.build.wiki_mirror` → `... scripts.cli mirror`. Add one sentence to README.md's pipeline section introducing the facade: "All pipeline commands go through `python -m scripts.cli` (run bare for the command list); the phase-module paths below describe where the code lives." Prose that describes code layout (e.g. the directory tree, `scripts/serve/retrieval.py` as a library) keeps module paths — do not convert those.

- [ ] **Step 3: Update `scripts/ingest/stage_candidate.py` module docstring**

The usage line (currently `python3 -m scripts.ingest.stage_candidate URL [--title T] [--note N] [--author A]`) becomes `python3 -m scripts.cli stage URL [--title T] [--note N] [--author A]`. Leave the provenance string at ~line 77 (`Appended by \`scripts.ingest.stage_candidate\`...`) unchanged — it labels the writing module, not a command.

- [ ] **Step 4: Check + commit**

```bash
make check
git status --short   # CLAUDE.md must NOT appear (gitignored)
git add README.md scripts/README.md scripts/ingest/stage_candidate.py
git commit -m "docs: route runnable commands through the scripts.cli facade

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Vault-guard test (TDD) + vault PROCESS doc sweep

**Files:**
- Modify: `tests/meta/test_cli_facade.py` (append guard test)
- Modify (vault, UNSTAGED, no commits): `~/Desktop/AI Safety/AI Safety/PROCESS_HEALTH_CHECK.md`, `~/Desktop/AI Safety/AI Safety/PROCESS_NEW_FILE.md`

**Interfaces:**
- Consumes: `vault_path()` from `scripts.wiki_lib.locations`; the existing autouse `_skip_if_no_vault` fixture in `tests/conftest.py` (it skips `needs_vault`-marked tests when the vault is absent — verify the marker name by reading the fixture before relying on it).
- Produces: the enforcement mechanism cited by CLAUDE.md §11.

- [ ] **Step 1: Append the failing guard test to `tests/meta/test_cli_facade.py`**

```python
import re

from scripts.wiki_lib.locations import vault_path

PROCESS_DOCS = ("PROCESS_HEALTH_CHECK.md", "PROCESS_NEW_FILE.md", "PROCESS_QUERY.md")
_RAW_PHASE_CMD = re.compile(r"python3? -m scripts\.(build|serve|ingest|maintenance)\b")


@pytest.mark.needs_vault
def test_process_docs_call_only_the_facade():
    """Vault PROCESS docs must invoke scripts.cli, never phase modules
    directly (CLAUDE.md §11). Prose paths like scripts/build/index.py are
    fine — only runnable `python -m scripts.<phase>` commands are banned."""
    vault = vault_path()
    offenders = []
    for doc in PROCESS_DOCS:
        path = vault / doc
        if not path.exists():
            pytest.skip(f"{doc} not present in vault")
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _RAW_PHASE_CMD.search(line):
                offenders.append(f"{doc}:{lineno}: {line.strip()}")
    assert not offenders, (
        "PROCESS docs must call `python -m scripts.cli <command>`, "
        "not phase modules directly:\n" + "\n".join(offenders)
    )
```

- [ ] **Step 2: Run it to verify it fails (RED)**

Run: `uv run --extra test pytest tests/meta/test_cli_facade.py::test_process_docs_call_only_the_facade -v`
Expected: FAIL, listing ~6 offender lines in PROCESS_HEALTH_CHECK.md (the `--directory ... python -m scripts.maintenance.check_vocab_sync` etc. lines from the restructure sweep). If it SKIPS, the vault marker/fixture wiring is wrong — fix before proceeding.

- [ ] **Step 3: Sweep the vault docs (edits stay unstaged; nothing else in the vault touched)**

`grep -nE "python3? -m scripts\.(build|serve|ingest|maintenance)" ~/Desktop/AI\ Safety/AI\ Safety/PROCESS_HEALTH_CHECK.md ~/Desktop/AI\ Safety/AI\ Safety/PROCESS_NEW_FILE.md` and convert each hit, preserving the `uv run --directory ~/Documents/Claude/Projects/AI\ Safety` wrapper and all flags:

- `python -m scripts.maintenance.check_vocab_sync` → `python -m scripts.cli vocab-sync`
- `python -m scripts.maintenance.cleanup_metadata --apply` → `python -m scripts.cli cleanup --apply`
- `python -m scripts.build.index --no-detail-md` → `python -m scripts.cli build --no-detail-md`
- `python -m scripts.build.wiki_mirror` → `python -m scripts.cli mirror`
- `--extra semantic ... python -m scripts.build.embeddings` → `--extra semantic ... python -m scripts.cli embed`
- any `python3 -m scripts.ingest.stage_candidate ...` → `python3 -m scripts.cli stage ...`

Table/prose references to module PATHS (`scripts/build/index.py` in the §12 inventory table, `scripts/serve/mcp_tools/`, `scripts/wiki_lib/...`) stay — they describe where code lives, and the guard regex deliberately doesn't match them.

- [ ] **Step 4: Run the guard test to verify it passes (GREEN)**

Run: `uv run --extra test pytest tests/meta/test_cli_facade.py -v`
Expected: 6 passed (5 from Task 1 + guard).

- [ ] **Step 5: Commit (code repo only)**

```bash
make fmt && make lint && make check
git add tests/meta/test_cli_facade.py
git commit -m "test(cli): vault-guard test — PROCESS docs may only call the facade

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git -C ~/Desktop/"AI Safety"/"AI Safety" status --short | head   # PROCESS docs modified, unstaged — expected
```

---

### Task 4: End-to-end verification, digest-task line, finish branch

**Files:** none (verification only)

- [ ] **Step 1: Full suite**

Run: `make check`
Expected: 174 passed + 1 skipped (168 baseline + 6 facade tests).

- [ ] **Step 2: Live facade smokes**

```bash
cd "/Users/harlem/Documents/Claude/Projects/AI Safety"
uv run python -m scripts.cli                       # table, exit 0
uv run python -m scripts.cli vocab-sync            # exit 0, "in sync"
uv run python -m scripts.cli query "RLHF" | head -8   # ranked hits
uv run python -m scripts.cli nope; echo "exit: $?"    # table to stderr, exit: 2
cd /tmp && uv run --directory "/Users/harlem/Documents/Claude/Projects/AI Safety" python -m scripts.cli vocab-sync   # foreign-cwd form used by vault docs
```

- [ ] **Step 3: Produce the digest-task replacement line for the user**

Include verbatim in the final report (the user pastes it into the claude.ai scheduled-task instructions; only they can edit it):

> Stage each ingest candidate with:
> `uv run --directory "<path to the repo checkout>" python -m scripts.cli stage URL [--title T] [--note N] [--author A]`
> (In the cloud sandbox the repo checkout root is the working directory, so plain `python3 -m scripts.cli stage URL ...` from there also works.)

- [ ] **Step 4: Finish the branch**

Use superpowers:finishing-a-development-branch — verify tests, present the 4 options (merge locally / PR / keep / discard). If PR: push `feat/cli-facade`, `gh pr create` against main, body ends with the standard generation footer.

---

## Self-review notes

- Spec §1 table+mechanism → Task 1 (code verbatim from spec's decisions; all 11 targets pre-verified to have `__main__` guards). Spec §2 contract → Task 2 Step 1. Spec §3 references → Task 2 Steps 2–3 (repo) + Task 3 Step 3 (vault) + Task 4 Step 3 (digest line). Spec §4 tests → Task 1 Step 1 (four facade tests) + Task 3 Step 1 (guard).
- Deviation from spec §3: no vault `log.md` entry this time (command-form swap is cosmetic; the restructure entry already tells the story). Global Constraints records this.
- Forwarding test runs in a subprocess to avoid runpy's already-imported RuntimeWarning — noted in the test docstring.
- Type consistency: `COMMANDS: dict[str, tuple[str, str]]` and `main(argv)` match across Tasks 1–3; expected test counts (5 → 6) and suite totals (173+1 → 174+1) are consistent.
