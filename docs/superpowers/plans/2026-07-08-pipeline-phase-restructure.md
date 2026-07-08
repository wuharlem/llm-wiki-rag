# Pipeline-Phase Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize flat `scripts/` and `tests/` into pipeline-phase packages (`ingest/build/serve/maintenance`), split the 1033-line MCP server into an app core + `mcp_tools/` modules, and sweep every reference (repo docs, vault PROCESS docs, Claude Desktop MCP registration).

**Architecture:** `scripts/` becomes a real Python package run via `python -m scripts.<phase>.<module>` from the repo root. `wiki_lib` is addressed as `scripts.wiki_lib` everywhere. The MCP server keeps its exact external contract (tool names, kwargs, error envelope) and re-exports every tool + input model from `scripts.serve.mcp_server` so tests and consumers have one stable surface.

**Tech Stack:** Python 3.10+, uv, pytest, ruff, FastMCP, Pydantic v2.

**Spec:** `docs/superpowers/specs/2026-07-08-scripts-restructure-design.md`

## Global Constraints

- **Contract §4 frozen:** tool names, kwargs, defaults, `ConfigDict(extra="forbid")`, `_wrap_errors` INNER under `@mcp.tool(...)` OUTER, `{"ok": false, "error", "detail"}` envelope, stable codes (`index_not_built`, `file_not_found`, `vault_not_found`, `rebuild_timeout`). Zero external behavior change.
- **No dual import identity:** after Task 2, `scripts` must NOT be on `sys.path` as a root (pytest `pythonpath = [".", "tests"]`), or `wiki_lib.schema` and `scripts.wiki_lib.schema` become two module instances with two singleton caches.
- **`git mv` for every move** — history must follow.
- **Vault docs and code change in the same working session** (CLAUDE.md cross-folder rule). Vault edits are plain file edits (the vault is not in this git repo).
- **CLAUDE.md is gitignored** (untracked since d255f41): edit the file, but it will not appear in commits — that is expected.
- Run `make fmt && make lint` before each commit (user's standing rule).
- All work on branch `refactor/pipeline-phase-layout` (already created).

---

### Task 1: Restructure `tests/` into phase folders

**Files:**
- Move (git mv): 27 `tests/test_*.py` files into `tests/{wiki_lib,build,serve,meta}/`
- Unchanged: `tests/conftest.py` stays at `tests/` root

**Interfaces:**
- Consumes: nothing (pure moves; imports still resolve via existing `pythonpath = ["scripts", "tests"]`)
- Produces: the folder layout Tasks 2–3 assume when editing test files (`tests/serve/test_mcp_input_validation.py` etc.)

- [ ] **Step 1: Record the baseline test count**

```bash
cd "/Users/harlem/Documents/Claude/Projects/AI Safety"
uv run --extra test pytest --collect-only -q | tail -2
```

Note the `N tests collected` number (some may show as deselected/skipped — record the total).

- [ ] **Step 2: Create folders and move files**

```bash
mkdir -p tests/wiki_lib tests/build tests/serve tests/meta

git mv tests/test_wiki_schema_loader.py tests/test_config_loader.py \
       tests/test_frontmatter_lib.py tests/test_split_frontmatter.py \
       tests/test_paths_lib.py tests/test_indexable_path_invariant.py \
       tests/test_meta_doc_filter.py tests/test_path_resolver.py \
       tests/test_retrieval_context.py tests/test_wiki_lib_smoke.py \
       tests/wiki_lib/

git mv tests/test_chunking.py tests/test_emit_manifest.py \
       tests/test_build_smoke.py tests/test_manifest_schema.py \
       tests/test_audit_files_excluded_regression.py \
       tests/test_embeddings_alignment.py \
       tests/build/

git mv tests/test_bm25.py tests/test_rrf.py tests/test_filters.py \
       tests/test_search_smoke.py tests/test_save_query.py \
       tests/test_count_files_by_field.py \
       tests/test_invalidate_caches_integration.py \
       tests/test_mcp_input_validation.py tests/test_mcp_error_envelope.py \
       tests/serve/

git mv tests/test_claude_md_contracts.py tests/test_e2e_build_and_search.py \
       tests/meta/
```

Do NOT create `__init__.py` under `tests/` — basenames are unique, pytest's default import mode handles this, and root `conftest.py` scopes to all subfolders automatically.

- [ ] **Step 3: Verify collection count is unchanged**

```bash
uv run --extra test pytest --collect-only -q | tail -2
```

Expected: same total as Step 1. If pytest errors with "import file mismatch", delete stale caches: `find tests -name __pycache__ -exec rm -rf {} +` and re-run.

- [ ] **Step 4: Run the full suite**

```bash
make check
```

Expected: PASS (same skips as before).

- [ ] **Step 5: Commit**

```bash
git add -A tests/
git commit -m "refactor(tests): mirror pipeline phases — wiki_lib/, build/, serve/, meta/

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Move scripts into phase packages, rewrite imports, fix path derivations

This is the atomic core. It cannot be split and stay green, because flipping the import spelling (`wiki_lib` → `scripts.wiki_lib`) and pytest's `pythonpath` is global.

**Files:**
- Create: `scripts/__init__.py`, `scripts/ingest/__init__.py`, `scripts/build/__init__.py`, `scripts/serve/__init__.py`, `scripts/maintenance/__init__.py` (each: a one-line docstring, e.g. `"""Ingest phase: URL fetching, staging, dedup."""`)
- Move (git mv), per spec §1 table: 12 scripts → phase folders, 3 renamed (`build_index→build/index`, `build_embeddings→build/embeddings`, `build_wiki_index→build/wiki_mirror`, `wiki_retrieval→serve/retrieval`, `query_index→serve/query_cli`, `wiki_mcp_server→serve/mcp_server`)
- Modify: every `.py` under `scripts/` and `tests/` that imports project modules; `pyproject.toml`
- Test: the whole existing suite (`make check`)

**Interfaces:**
- Consumes: Task 1's `tests/` layout.
- Produces: package paths every later task relies on — `scripts.wiki_lib.*`, `scripts.build.index`, `scripts.build.wiki_mirror`, `scripts.build.embeddings`, `scripts.serve.retrieval`, `scripts.serve.query_cli`, `scripts.serve.mcp_server` (module attrs: `mcp`, `MCP_SERVER_NAME`, `main`, all tool fns + input models — unchanged names), `scripts.ingest.{fetch,stage_candidate,dedup_report}`, `scripts.maintenance.{cleanup_metadata,check_vocab_sync,regenerate_notion_sources}`.
- Invocation everywhere becomes `uv run python -m scripts.<phase>.<module>` from the repo root.

- [ ] **Step 1: Create packages and move files**

```bash
cd "/Users/harlem/Documents/Claude/Projects/AI Safety"
mkdir -p scripts/ingest scripts/build scripts/serve scripts/maintenance
printf '"""Build+serve pipeline for the LLM-maintained wiki (package root)."""\n' > scripts/__init__.py
printf '"""Ingest phase: URL fetching, staging, dedup."""\n' > scripts/ingest/__init__.py
printf '"""Build phase: chunked index, embeddings, Obsidian mirror."""\n' > scripts/build/__init__.py
printf '"""Serve phase: retrieval library, query CLI, MCP server."""\n' > scripts/serve/__init__.py
printf '"""Maintenance: metadata cleanup, vocab lint, Notion CSV regen."""\n' > scripts/maintenance/__init__.py

git mv scripts/fetch.py scripts/ingest/fetch.py
git mv scripts/stage_candidate.py scripts/ingest/stage_candidate.py
git mv scripts/dedup_report.py scripts/ingest/dedup_report.py
git mv scripts/build_index.py scripts/build/index.py
git mv scripts/build_embeddings.py scripts/build/embeddings.py
git mv scripts/build_wiki_index.py scripts/build/wiki_mirror.py
git mv scripts/wiki_retrieval.py scripts/serve/retrieval.py
git mv scripts/query_index.py scripts/serve/query_cli.py
git mv scripts/wiki_mcp_server.py scripts/serve/mcp_server.py
git mv scripts/cleanup_metadata.py scripts/maintenance/cleanup_metadata.py
git mv scripts/check_vocab_sync.py scripts/maintenance/check_vocab_sync.py
git mv scripts/regenerate_notion_sources.py scripts/maintenance/regenerate_notion_sources.py
git add scripts/__init__.py scripts/*/__init__.py
```

- [ ] **Step 2: Rewrite import statements mechanically**

Patterns allow leading whitespace (several tests import inside functions):

```bash
perl -pi -e '
  s/^(\s*)from wiki_lib(\.|\s)/${1}from scripts.wiki_lib${2}/;
  s/^(\s*)import wiki_lib\./${1}import scripts.wiki_lib./;
  s/^(\s*)import wiki_retrieval as (\w+)/${1}from scripts.serve import retrieval as ${2}/;
  s/^(\s*)import wiki_retrieval$/${1}from scripts.serve import retrieval as wiki_retrieval/;
  s/^(\s*)from wiki_retrieval import/${1}from scripts.serve.retrieval import/;
  s/^(\s*)import build_index as (\w+)/${1}from scripts.build import index as ${2}/;
  s/^(\s*)import build_index$/${1}from scripts.build import index as build_index/;
  s/^(\s*)from build_index import/${1}from scripts.build.index import/;
  s/^(\s*)import wiki_mcp_server as (\w+)/${1}from scripts.serve import mcp_server as ${2}/;
  s/^(\s*)import wiki_mcp_server$/${1}import scripts.serve.mcp_server as wiki_mcp_server/;
' $(git ls-files "scripts/*.py" "scripts/**/*.py" "tests/**/*.py" "tests/*.py")
```

Note the `import ... as config_module` form in `tests/wiki_lib/test_config_loader.py` (`import wiki_lib.config as config_module`) is covered by pattern 2 → `import scripts.wiki_lib.config as config_module` (binds `config_module`, unchanged semantics).

- [ ] **Step 3: Delete the sys.path hacks**

Three files carry `sys.path.insert(0, str(Path(__file__).resolve().parent))` (plus a comment line above). Remove hack + comment in:
- `scripts/serve/mcp_server.py` (~line 36–37)
- `scripts/maintenance/check_vocab_sync.py` (~line 33)
- `scripts/build/embeddings.py` (~line 36)

If `sys`/`Path` become unused imports in any of them, ruff will flag it — remove the dead import.

- [ ] **Step 4: Fix `__file__`-relative WORKDIR derivations (they now point at `scripts/`, not the repo root)**

In `scripts/build/index.py` (was lines 62–63), `scripts/build/wiki_mirror.py` (was 27–28), `scripts/serve/retrieval.py` (was 43–44), replace:

```python
SCRIPT_DIR = Path(__file__).resolve().parent
WORKDIR = SCRIPT_DIR.parent
```

with:

```python
WORKDIR = work_path()
```

and extend the existing locations import in each file: `from scripts.wiki_lib.locations import vault_path` → `from scripts.wiki_lib.locations import vault_path, work_path`. Delete `SCRIPT_DIR` only if nothing else uses it (grep each file first: `grep -n SCRIPT_DIR <file>`).

In `scripts/serve/mcp_server.py` (was line 733), replace:

```python
    state_path = Path(__file__).resolve().parent.parent / "01_data" / "index" / "source_state.json"
```

with:

```python
    state_path = work_path() / "01_data" / "index" / "source_state.json"
```

adding `from scripts.wiki_lib.locations import work_path` to the module's imports.

- [ ] **Step 5: Fix the rebuild_index subprocess invocations in `scripts/serve/mcp_server.py`**

Replace (was lines 762–763):

```python
    script = Path(__file__).resolve().parent / "build_index.py"
    cmd = [sys.executable, str(script)]
```

with:

```python
    cmd = [sys.executable, "-m", "scripts.build.index"]
```

and add `cwd=str(work_path()),` to the `subprocess.run(cmd, ...)` call (was line 769) so `-m` resolves the package regardless of the server's own cwd.

Replace (was lines 797–800):

```python
        mirror_script = Path(__file__).resolve().parent / "build_wiki_index.py"
        ...
            mproc = subprocess.run(
                [sys.executable, str(mirror_script)],
```

with:

```python
            mproc = subprocess.run(
                [sys.executable, "-m", "scripts.build.wiki_mirror"],
                cwd=str(work_path()),
```

keeping `capture_output`, `text`, and both timeouts exactly as they are. Also update the nearby string literal `"build_wiki_index.py timed out after 5 min"` → `"scripts.build.wiki_mirror timed out after 5 min"`.

- [ ] **Step 6: Update `pyproject.toml`**

```toml
[project.scripts]
wiki-mcp = "scripts.serve.mcp_server:main"
```

```toml
[tool.pytest.ini_options]
# Repo root on sys.path so tests import the `scripts` package
# (e.g. `from scripts.serve import retrieval`). tests/ stays importable
# for shared helpers. Do NOT re-add "scripts" here — that would make every
# module importable under two names and duplicate the schema/config
# singleton caches.
pythonpath = [".", "tests"]
```

```toml
[tool.ruff.lint.per-file-ignores]
# CLI entrypoints keep argparse/main blocks after module docstrings.
"scripts/**/*.py" = ["E402"]
```

(After the sys.path hacks are gone this ignore may be removable — try deleting it, run `make lint`; keep it only if violations remain.)

- [ ] **Step 7: Fix the module-identity check in `tests/meta/test_claude_md_contracts.py`**

The extra-forbid scan (was lines 43–58) filters classes with `cls.__module__ != "wiki_mcp_server"`. Make it survive both this task and Task 3's split:

```python
    import scripts.serve.mcp_server as wiki_mcp_server

    for name, cls in inspect.getmembers(wiki_mcp_server, inspect.isclass):
        ...
        # Filter to classes defined in the serve package (not re-imports).
        if not cls.__module__.startswith("scripts.serve"):
            continue
```

- [ ] **Step 8: Update runnable-command docstrings inside the moved files**

```bash
grep -rn "scripts/[a-z_]*\.py\|python scripts/" scripts --include="*.py"
```

For each hit in a module docstring / usage string (e.g. `fetch.py`'s `uv run python scripts/fetch.py`), rewrite to the `-m` form (`uv run python -m scripts.ingest.fetch`). Comments that merely *mention* an old filename (e.g. the `build_index.py --md-only` history notes in `mcp_server.py`) get the new module path too.

- [ ] **Step 9: Leftover scan — must be empty**

```bash
grep -rnE "^\s*(from|import) (wiki_lib|wiki_retrieval|build_index|build_wiki_index|build_embeddings|wiki_mcp_server|query_index)\b" scripts tests --include="*.py"
```

Expected: no output.

- [ ] **Step 10: Full check + CLI smoke**

```bash
make check
uv run python -m scripts.serve.query_cli --help
uv run python -m scripts.maintenance.check_vocab_sync
```

Expected: `make check` PASS; query_cli prints usage; check_vocab_sync exits 0 ("in sync").

- [ ] **Step 11: Commit**

```bash
make fmt && make lint
git add -A scripts/ tests/ pyproject.toml
git commit -m "refactor(scripts): pipeline-phase packages, python -m invocation

scripts/{ingest,build,serve,maintenance}/ with renamed modules
(build/index, build/wiki_mirror, serve/retrieval, serve/query_cli,
serve/mcp_server). wiki_lib now addressed as scripts.wiki_lib.
WORKDIR derivations moved to locations.work_path(); sys.path hacks
removed; rebuild_index subprocesses invoke -m module paths.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Split the MCP server into app core + `mcp_tools/`

**Files:**
- Create: `scripts/serve/mcp_app.py`, `scripts/serve/mcp_tools/__init__.py`, `scripts/serve/mcp_tools/search.py`, `scripts/serve/mcp_tools/browse.py`, `scripts/serve/mcp_tools/write.py`, `scripts/serve/mcp_tools/admin.py`
- Modify: `scripts/serve/mcp_server.py` (shrinks to entrypoint + re-export surface), `tests/meta/test_claude_md_contracts.py`
- Test: `tests/serve/test_mcp_input_validation.py`, `tests/serve/test_mcp_error_envelope.py`, `tests/meta/test_claude_md_contracts.py` (all existing — they are the regression harness)

**Interfaces:**
- Consumes: `scripts.serve.retrieval` (as `wr`), `scripts.wiki_lib.schema.get_schema`, `scripts.wiki_lib.locations.work_path`, `scripts.wiki_lib.source_state`.
- Produces: `scripts.serve.mcp_app` exporting `mcp` (FastMCP), `MCP_SERVER_NAME` (str), `_error_envelope(code: str, detail: str) -> str`, `_wrap_errors(fn)`. Each `mcp_tools/*` module defines its input models + tool functions at module level (decorated, therefore registered on import). `scripts.serve.mcp_server` re-exports EVERYTHING tests use: `mcp`, `MCP_SERVER_NAME`, `_error_envelope`, `_wrap_errors`, all 12 tool functions, all 8 input models.

- [ ] **Step 1: Update the contracts test to scan the tools package (write the failing test first)**

In `tests/meta/test_claude_md_contracts.py`, replace the extra-forbid scan's module source and filter:

```python
    from scripts.serve.mcp_tools import admin, browse, search, write

    offenders = []
    for mod in (admin, browse, search, write):
        for name, cls in inspect.getmembers(mod, inspect.isclass):
            if not (isinstance(cls, type) and issubclass(cls, BaseModel)) or cls is BaseModel:
                continue
            if not cls.__module__.startswith("scripts.serve.mcp_tools"):
                continue
            if cls.model_config.get("extra") != "forbid":
                offenders.append(name)
```

(Keep the existing assertion message. Preserve any other filtering the current test does — read it before editing.)

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run --extra test pytest tests/meta/test_claude_md_contracts.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.serve.mcp_tools'`.

- [ ] **Step 3: Create `scripts/serve/mcp_app.py`**

Move (cut, don't copy) from `mcp_server.py`: the error-envelope comment block, `_error_envelope`, `_wrap_errors`, the `MCP_SERVER_NAME` derivation + its comment, and `mcp = FastMCP(MCP_SERVER_NAME)`:

```python
"""FastMCP app core: server instance, name derivation, canonical error envelope.

Tool implementations live in scripts/serve/mcp_tools/; the runnable
entrypoint is scripts/serve/mcp_server.py.
"""

from __future__ import annotations

import functools
import json
from typing import Callable

from mcp.server.fastmcp import FastMCP

from scripts.wiki_lib.schema import get_schema

# ... (moved comment block + _error_envelope + _wrap_errors verbatim) ...

MCP_SERVER_NAME = f"{get_schema().wiki.slug.replace('-', '_')}_wiki_mcp"

mcp = FastMCP(MCP_SERVER_NAME)
```

- [ ] **Step 4: Create the four tool modules (move code verbatim, add imports)**

Split by the section map (line numbers from the pre-Task-2 file, same order in the current file):

| Module | Moves (models + tools) |
|---|---|
| `mcp_tools/search.py` | `SearchInput`, `FileDetailInput`, `MultiQueryInput`; `search_wiki`, `get_file_detail`, `multi_query_search` |
| `mcp_tools/browse.py` | `ListInput`, `FindRelatedConceptsInput`; `list_categories`, `list_concepts`, `list_tags`, `find_related_concepts`, `index_stats` |
| `mcp_tools/write.py` | `SaveQueryInput`, `AppendLogInput`, `AppendOpenQuestionInput`; `save_query`, `append_log`, `append_open_question` |
| `mcp_tools/admin.py` | `RebuildIndexInput`; `rebuild_index` (incl. its `subprocess`/`time`/`source_state` function-local imports and the `state_path`/debounce logic) |

Each module's header:

```python
from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from scripts.serve import retrieval as wr
from scripts.serve.mcp_app import _error_envelope, _wrap_errors, mcp
```

(Trim per module to what it actually uses — ruff will flag unused imports. `admin.py` also needs `import sys`, `from pathlib import Path` if still used, and `from scripts.wiki_lib.locations import work_path`.)

Decorator order stays exactly: `@mcp.tool(name=..., ...)` OUTER, `@_wrap_errors` INNER, function under both.

`mcp_tools/__init__.py` — importing the package registers every tool on the shared `mcp` instance:

```python
"""MCP tool implementations, grouped by concern. Importing this package
registers all tools on scripts.serve.mcp_app.mcp."""

from scripts.serve.mcp_tools import admin, browse, search, write  # noqa: F401
```

- [ ] **Step 5: Shrink `scripts/serve/mcp_server.py` to entrypoint + re-export surface**

```python
"""Runnable MCP server entrypoint (uv run python -m scripts.serve.mcp_server).

Re-exports the full tool surface so tests and external callers keep a single
stable import point: `from scripts.serve import mcp_server as ws`.
"""

from __future__ import annotations

from scripts.serve.mcp_app import (  # noqa: F401
    MCP_SERVER_NAME,
    _error_envelope,
    _wrap_errors,
    mcp,
)
from scripts.serve.mcp_tools.admin import RebuildIndexInput, rebuild_index  # noqa: F401
from scripts.serve.mcp_tools.browse import (  # noqa: F401
    FindRelatedConceptsInput,
    ListInput,
    find_related_concepts,
    index_stats,
    list_categories,
    list_concepts,
    list_tags,
)
from scripts.serve.mcp_tools.search import (  # noqa: F401
    FileDetailInput,
    MultiQueryInput,
    SearchInput,
    get_file_detail,
    multi_query_search,
    search_wiki,
)
from scripts.serve.mcp_tools.write import (  # noqa: F401
    AppendLogInput,
    AppendOpenQuestionInput,
    SaveQueryInput,
    append_log,
    append_open_question,
    save_query,
)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the MCP test files, then the full suite**

```bash
uv run --extra test pytest tests/serve/test_mcp_input_validation.py tests/serve/test_mcp_error_envelope.py tests/meta/test_claude_md_contracts.py -v
make check
```

Expected: PASS. If FastMCP raises "tool already registered" the re-export chain imported a tool module twice under different names — check that nothing imports `mcp_tools.search` as a top-level `search` module.

- [ ] **Step 7: Commit**

```bash
make fmt && make lint
git add -A scripts/serve tests/meta
git commit -m "refactor(mcp): split server into mcp_app core + mcp_tools/{search,browse,write,admin}

External contract unchanged: same tool names, kwargs, extra=forbid,
_wrap_errors envelope. mcp_server.py is now the entrypoint and the
stable re-export surface.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Repo docs sweep (README ×2, CLAUDE.md, Makefile verify)

**Files:**
- Modify: `README.md`, `scripts/README.md`, `CLAUDE.md` (gitignored — edit, won't commit)
- Verify-only: `Makefile`

**Interfaces:**
- Consumes: final module paths from Tasks 2–3.
- Produces: docs that match the tree; Task 5 copies its command forms from here.

- [ ] **Step 1: Sweep both READMEs**

```bash
grep -n "scripts/" README.md scripts/README.md
```

For every runnable command, rewrite to `-m` form. Known lines in `README.md` (verify each, numbers may have drifted): 33, 55, 63–64, 72–73, 81, 88. E.g.:

- `uv run python scripts/build_index.py` → `uv run python -m scripts.build.index`
- `uv run --extra all python scripts/build_embeddings.py` → `uv run --extra all python -m scripts.build.embeddings`
- `uv run python scripts/query_index.py "RLHF"` → `uv run python -m scripts.serve.query_cli "RLHF"`
- `uv run python scripts/wiki_mcp_server.py` → `uv run python -m scripts.serve.mcp_server`
- `uv run python scripts/fetch.py [--sample 3] ...` → `uv run python -m scripts.ingest.fetch [--sample 3] ...`
- `uv run python scripts/build_wiki_index.py` → `uv run python -m scripts.build.wiki_mirror`
- prose: `scripts/cleanup_metadata.py` → `scripts/maintenance/cleanup_metadata.py`, etc.

Update the layout tree in `README.md` (~line 46) to show the four phase folders. Give `scripts/README.md` the same treatment end-to-end (it documents fetch setup in detail).

- [ ] **Step 2: Sweep CLAUDE.md `path:line` citations**

For each cited symbol, recompute: `grep -n "<symbol>" <new path>`. Sections to touch (from the spec §4): §1 (`scripts/check_vocab_sync.py` → `scripts/maintenance/check_vocab_sync.py`), §2 (`paths.py:32` unchanged path — verify line; `wiki_retrieval.py:106` → `scripts/serve/retrieval.py:<n>`; `build_index.py` → `scripts/build/index.py`), §3 (`build_index.py:634/621/631` → `scripts/build/index.py:<n>` ×3), §4 (`scripts/wiki_mcp_server.py` → `scripts/serve/mcp_server.py`, note the `mcp_tools/` layout and that `_wrap_errors` lives in `scripts/serve/mcp_app.py`), §5 (`fetch.py:47–48` → `scripts/ingest/fetch.py:<n>`), §7 (one-shot convention — verify unchanged wording still true; it is, `scripts/_oneshot_*.py` still works), §9 (both module tables), §10 (consumer list gets new paths; `wiki_retrieval.VAULT_PATH` → `scripts.serve.retrieval.VAULT_PATH`).

- [ ] **Step 3: Verify Makefile needs no changes**

```bash
grep -n "scripts\|tests" Makefile
```

`ruff format scripts/ tests/` and `ruff check scripts/ tests/` are directory-recursive — expected: no edit needed. If anything references a specific file, update it.

- [ ] **Step 4: Check + commit**

```bash
make check
git add README.md scripts/README.md
git commit -m "docs: update all script invocations to python -m phase-package form

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

(CLAUDE.md is edited but untracked — verify with `git status` that it doesn't appear.)

---

### Task 5: Vault PROCESS docs sweep

**Files:**
- Modify: `~/Desktop/AI Safety/AI Safety/PROCESS_HEALTH_CHECK.md`, `~/Desktop/AI Safety/AI Safety/PROCESS_NEW_FILE.md`
- Append: `~/Desktop/AI Safety/AI Safety/log.md`
- Untouched: `PROCESS_QUERY.md` (verified: MCP tool names only)

**Interfaces:**
- Consumes: command forms finalized in Task 4.
- Produces: vault docs whose shell fallbacks actually run post-restructure.

Vault-doc commands must work from ANY cwd (audits run with the vault as cwd), so use the `--directory` form, not bare `python3`:

```
uv run --directory ~/Documents/Claude/Projects/AI\ Safety python -m scripts.<phase>.<module>
```

- [ ] **Step 1: PROCESS_HEALTH_CHECK.md**

```bash
grep -n "scripts/\|build_index\|build_wiki_index\|build_embeddings\|query_index\|wiki_mcp_server\|wiki_retrieval\|check_vocab_sync\|cleanup_metadata\|dedup_report\|regenerate_notion" ~/Desktop/AI\ Safety/AI\ Safety/PROCESS_HEALTH_CHECK.md
```

Edit every hit (~25; found at lines 21, 29, 39, 68, 113, 121, 201, 212, 241, 249, 257, 332–357, 397–411, 430, 451–466, 500–504 — re-grep, don't trust these numbers):

- Runnable commands → the `--directory` `-m` form above. Specifically: `python3 scripts/check_vocab_sync.py` (×2), `python3 scripts/cleanup_metadata.py --apply`, `python3 scripts/build_index.py --no-detail-md`, `python3 scripts/build_wiki_index.py` (×2), `uv run --extra semantic python scripts/build_embeddings.py`.
- The §3 "Live scripts" inventory (line ~29) and the script reference table (~451–466): new paths + renamed files (`scripts/build/index.py`, `scripts/build/wiki_mirror.py`, `scripts/serve/retrieval.py`, `scripts/serve/query_cli.py`, `scripts/serve/mcp_server.py` (+ `mcp_app.py`, `mcp_tools/`), `scripts/ingest/...`, `scripts/maintenance/...`). Helper row `wiki_lib/source_state.py` → `scripts/wiki_lib/source_state.py`.
- Prose filename mentions (`build_index.py::process_pdf`, `wiki_lib/paths.py:is_indexable_path`, `wiki_retrieval.py`, …) → new paths.
- One-shot convention lines (212, 241, 257, 466): path stays `scripts/_oneshot_*.py` — no change.

- [ ] **Step 2: PROCESS_NEW_FILE.md**

Same grep, then edit the ~6 hits (lines ~68, 87, 146, 266, 374, 392): `scripts/query_index.py` → `scripts/serve/query_cli.py`, `build_index.py` → `scripts/build/index.py` (all mentions incl. the `--md-only` history note), `scripts/check_vocab_sync.py` → `scripts/maintenance/check_vocab_sync.py`, `scripts/wiki_lib/paths.py` — unchanged path, verify only.

- [ ] **Step 3: Append a note to the vault log**

Append to `~/Desktop/AI Safety/AI Safety/log.md`, matching its `## [YYYY-MM-DD] kind | title` format:

```markdown
## [2026-07-08] note | Pipeline repo restructured into phase packages

scripts/ reorganized: ingest/, build/, serve/, maintenance/ (+ wiki_lib unchanged).
All CLI invocations are now `uv run python -m scripts.<phase>.<module>` from the
repo root. MCP tool names/signatures unchanged. PROCESS_HEALTH_CHECK.md and
PROCESS_NEW_FILE.md shell commands updated to match.
```

(Direct file append, not the `append_log` MCP tool — the server isn't connected to this session.)

- [ ] **Step 4: Verify no stale references remain in the vault docs**

```bash
grep -rn "scripts/[a-z_]*\.py" ~/Desktop/AI\ Safety/AI\ Safety/PROCESS_*.md | grep -v "_oneshot_\|wiki_lib/"
```

Expected: no output (only `_oneshot_` convention and `scripts/wiki_lib/...` paths survive).

---

### Task 6: Update the Claude Desktop MCP registration

**Files:**
- Modify: `~/Library/Application Support/Claude/claude_desktop_config.json` (outside the repo — SHOW THE USER THE EXACT EDIT AND GET CONFIRMATION FIRST, per spec §2)

**Interfaces:**
- Consumes: `scripts.serve.mcp_server` entrypoint from Task 3.
- Produces: a registration that boots the restructured server.

- [ ] **Step 1: Show the user the diff and wait for approval**

Current entry (`mcpServers.ai-safety-wiki`):

```json
{
  "command": "uv",
  "args": ["run", "--directory", "/Users/harlem/Documents/Claude/Projects/AI Safety", "python", "scripts/wiki_mcp_server.py"]
}
```

Proposed:

```json
{
  "command": "uv",
  "args": ["run", "--directory", "/Users/harlem/Documents/Claude/Projects/AI Safety", "python", "-m", "scripts.serve.mcp_server"]
}
```

(`--directory` already pins cwd to the repo root, which is exactly what `-m` needs.)

- [ ] **Step 2: Apply the edit** (only the last arg changes: `"scripts/wiki_mcp_server.py"` → `"-m", "scripts.serve.mcp_server"` — note this is one arg becoming two)

- [ ] **Step 3: Tell the user Claude Desktop needs a restart to pick it up.** No commit (file is outside the repo).

---

### Task 7: End-to-end verification and branch finish

**Files:** none (verification only)

- [ ] **Step 1: Full suite**

```bash
make check
```

Expected: PASS.

- [ ] **Step 2: CLI retrieval smoke (real index)**

```bash
uv run python -m scripts.serve.query_cli "RLHF" 2>/dev/null | head -20
```

Expected: ranked hits with file_ids/scores (the local `01_data/index/` is built). Empty output or `index_not_built` = investigate before proceeding.

- [ ] **Step 3: Exercise the server surface incl. the subprocess paths**

```bash
uv run python -c "
import json
from scripts.serve import mcp_server as ws
stats = json.loads(ws.index_stats())
print('n_files:', stats.get('n_files'), 'degraded:', stats.get('degraded'))
out = json.loads(ws.rebuild_index(ws.RebuildIndexInput(force=True)))
print('rebuild ok:', out.get('ok'), 'mirror ok:', out.get('mirror', {}).get('ok'))
"
```

Expected: sensible `n_files`, `degraded: False`; then `rebuild ok: True`, `mirror ok: True` (~40s — this proves the `-m` subprocess invocations and `work_path()` state-file fix). A `rebuild ok: False` with stderr mentioning `No module named scripts` means the `cwd=` kwarg is missing on a `subprocess.run`.

- [ ] **Step 4: Boot the actual server binary path**

```bash
cd "/Users/harlem/Documents/Claude/Projects/AI Safety" && timeout 5 uv run python -m scripts.serve.mcp_server; echo "exit: $?"
```

Expected: `exit: 124` (server ran until timeout killed it — i.e., it boots and blocks on stdio). Any other exit code = boot crash; read the traceback.

- [ ] **Step 5: Repo-wide stale-reference sweep**

```bash
grep -rn "wiki_mcp_server\.py\|wiki_retrieval\.py\|build_index\.py\|build_wiki_index\.py\|query_index\.py\|build_embeddings\.py" \
  README.md scripts/README.md CLAUDE.md Makefile pyproject.toml scripts tests --include="*.py" -r
```

Expected: no output, except historical references that are *supposed* to stay (e.g. `CODE_AUDIT_2026-04-30.md` citations, git-history mentions in README's "recover any of them" paragraph — judgment call: past-tense history references keep old names).

- [ ] **Step 6: Finish the branch**

Use superpowers:finishing-a-development-branch — present merge/PR options to the user. If PR: push `refactor/pipeline-phase-layout`, open PR with `gh pr create`, body ending with the standard generation footer.

---

## Self-review notes

- Spec §1 layout → Task 2 Step 1. Spec §2 mechanics → Task 2 Steps 2–6 (incl. the three WORKDIR traps and `source_state.json` path the spec didn't know about — found during planning). Spec §3 split → Task 3. Spec §4 sweep → Tasks 4–6. Spec §5 verification → Task 7. Spec §6 tests → Task 1.
- Deviation from spec: spec placed `_wrap_errors` in `mcp_server.py`; the plan puts it in `mcp_app.py` (tool modules must import it without circularity) and re-exports it from `mcp_server` — external surface identical.
- Type consistency: `ws.RebuildIndexInput(force=True)` matches the model moved in Task 3 (`RebuildIndexInput` has `force: bool = False`); `work_path()` signature per `locations.py` public surface.
