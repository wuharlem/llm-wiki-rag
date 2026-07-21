"""MCP tool: rebuild_index."""

from __future__ import annotations

import json
import sys

from pydantic import BaseModel, ConfigDict, Field

from scripts.serve import retrieval as wr
from scripts.serve.mcp_app import _error_envelope, _wrap_errors, mcp
from scripts.wiki_lib.locations import work_path

# ---------------------------------------------------------------------------
# Maintenance tools — rebuild_index
# ---------------------------------------------------------------------------


class RebuildIndexInput(BaseModel):
    # NOTE: `md_only` was REMOVED from this tool (2026-07-03) after causing three
    # PDF-coverage regressions (2026-06-30/07-01/07-02): it rebuilt the index
    # without any PDF content — a drop, not an increment — leaving all PDFs
    # unsearchable until the next full rebuild. Full rebuilds take ~3s on a warm
    # cache, so the flag saved nothing. `extra="forbid"` means any caller still
    # passing md_only=true now fails loudly at validation instead of silently
    # degrading the index. The CLI flag `scripts.build.index --md-only` still exists
    # for cold-build debugging only.
    model_config = ConfigDict(extra="forbid")
    skip_detail_md: bool = Field(
        default=False,
        description="Skip writing per-file detail pages into _index/files/. Saves ~1s; only useful for very fast iteration.",
    )
    # Debounce (2026-07-04): rebuilds are skipped when no indexable source file
    # changed since the last successful rebuild (fingerprint: relpath+size+mtime
    # over indexable .md/.pdf, see wiki_lib/source_state.py). `force=True`
    # bypasses the check — use after CLI-side builds, suspected corruption, or
    # when index_stats reports degraded=true.
    force: bool = Field(
        default=False,
        description="Rebuild even if no source file changed since the last successful rebuild. Default False (skip redundant rebuilds).",
    )


@mcp.tool(
    name="rebuild_index",
    annotations={
        "title": "Rebuild the RAG index from the vault",
        "readOnlyHint": False,
        "destructiveHint": False,  # overwrites generated artifacts only
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@_wrap_errors
def rebuild_index(params: RebuildIndexInput) -> str:
    """Re-extract every source file in the vault and rewrite chunks.jsonl,
    index.json, manifest.csv, and the per-file detail pages under
    `_index/files/`. Subsequent runs are fast (~3s) because PDF text is
    cached by content hash; the first cold build takes 5-10 minutes.

    On success, also refreshes the Obsidian-side `_index/` mirror
    (scripts.build.wiki_mirror: master/category/concept/tag pages + prune of
    manifest-orphaned pages) — no separate mirror step needed since
    2026-07-04. Mirror status is returned in the payload's "mirror" block;
    a mirror failure never fails the rebuild. The graph.json artifact (file
    relatedness/communities/insights, built in-process by the index
    subprocess) is reported in the payload's "graph" block; a missing or
    stale graph never fails the rebuild either. The embeddings refresh
    (hash-delta incremental, also in-process, now BEFORE the graph stage so
    its embedding signal is fresh) is reported in the payload's "embeddings"
    block; a missing embeddings_meta.json (semantic extra not installed, or
    zero indexable chunks) never fails the rebuild either.

    Use this after adding new sources to the vault, or after running the
    `save_query` tool a few times — saved queries aren't searchable through
    `search_wiki` until the index is rebuilt.

    Drops the in-memory chunk cache and reloads on next search.

    Always a FULL rebuild (markdown + PDFs). The former `md_only` flag was
    removed 2026-07-03 — it silently dropped every PDF from the index.

    Debounced since 2026-07-04: if no indexable source file changed since the
    last successful rebuild (relpath+size+mtime fingerprint), the call returns
    `{"ok": true, "skipped": true, "reason": "sources_unchanged"}` without
    rebuilding, logging, or touching the mirror. Pass `force=true` to bypass
    (e.g. after a CLI-side `scripts.build.index` run, or when `index_stats`
    reports `degraded: true`).

    Args:
        params (RebuildIndexInput): skip_detail_md, force flags.

    Returns:
        str: JSON with build summary (n_files, n_chunks, elapsed_s, errors),
        or the skip payload described above.
        On failure, returns the canonical error envelope:
            {"ok": false, "error": "<code>", "detail": "<msg>"}
        Codes: `rebuild_timeout` (15 min subprocess timeout),
        `<ExceptionClassName>` (any other failure).
    """
    import subprocess
    import time

    from scripts.wiki_lib.source_state import (
        compute_source_state,
        read_saved_state,
        write_saved_state,
    )

    state_path = work_path() / "01_data" / "index" / "source_state.json"

    # Debounce: skip the rebuild when nothing indexable changed. Guarded on a
    # loadable, non-empty index so a missing/corrupt index always rebuilds.
    pre_build_digest: str | None = None
    try:
        pre_build_digest = compute_source_state(wr.VAULT_PATH)
    except Exception:  # noqa: BLE001 — fingerprint failure must never block a rebuild
        pre_build_digest = None
    if not params.force and pre_build_digest is not None:
        saved = read_saved_state(state_path)
        if saved == pre_build_digest:
            try:
                stats_now = wr.index_stats()
            except Exception:
                stats_now = {}
            if stats_now.get("n_chunks") and not stats_now.get("degraded"):
                return json.dumps(
                    {
                        "ok": True,
                        "skipped": True,
                        "reason": "sources_unchanged",
                        "detail": "No indexable source file changed since the last successful rebuild. Pass force=true to rebuild anyway.",
                        "stats": stats_now,
                    },
                    indent=2,
                    ensure_ascii=False,
                )

    cmd = [sys.executable, "-m", "scripts.build.index"]
    if params.skip_detail_md:
        cmd.append("--no-detail-md")

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,  # 15 min cap; cold PDF builds can hit this
            cwd=str(work_path()),
        )
    except subprocess.TimeoutExpired:
        return _error_envelope("rebuild_timeout", "rebuild_index timed out after 15 min")
    elapsed = time.time() - t0

    # Drop all cached state so subsequent search_wiki calls see the new index.
    wr.invalidate_caches()

    stats: dict = {}
    try:
        stats = wr.index_stats()
    except Exception:
        pass

    # Refresh the Obsidian-side `_index/` mirror (master/category/concept/tag
    # pages + prune of manifest-orphaned pages). Added 2026-07-04: rebuilds
    # used to leave the mirror stale until scripts.build.wiki_mirror was run by
    # hand — the 07-04 audit caught 5 orphan detail pages left behind by a
    # rebuild that wasn't followed by a mirror refresh (_audit_2026-07-04.md
    # §3). A mirror failure never fails the rebuild — it is reported in the
    # payload["mirror"] block and the log line instead.
    mirror: dict = {}
    if proc.returncode == 0:
        try:
            mproc = subprocess.run(
                [sys.executable, "-m", "scripts.build.wiki_mirror"],
                cwd=str(work_path()),
                capture_output=True,
                text=True,
                timeout=300,  # 5 min cap; typical run is ~5s
            )
            mirror = {
                "ok": mproc.returncode == 0,
                "stdout_tail": mproc.stdout[-500:] if mproc.stdout else "",
                "stderr_tail": mproc.stderr[-500:] if mproc.stderr else "",
            }
        except subprocess.TimeoutExpired:
            mirror = {
                "ok": False,
                "error": "mirror_timeout",
                "detail": "scripts.build.wiki_mirror timed out after 5 min",
            }
        except Exception as exc:  # noqa: BLE001 — mirror must never sink the rebuild
            mirror = {"ok": False, "error": type(exc).__name__, "detail": str(exc)}

    # Report graph.json artifact state. The graph itself was already built
    # in-process by the index subprocess (scripts.build.graph runs at the end
    # of scripts.build.index) — this block only *reports* what landed; a
    # missing/stale artifact must never fail the rebuild.
    graph: dict = {}
    if proc.returncode == 0:
        try:
            from scripts.serve.retrieval import GRAPH_PATH

            if GRAPH_PATH.exists():
                g = json.loads(GRAPH_PATH.read_text())
                graph = {
                    "ok": True,
                    "built_at": g.get("built_at"),
                    "n_edges": g.get("n_edges"),
                    "n_communities": g.get("n_communities"),
                }
            else:
                graph = {"ok": False, "detail": "graph.json not produced (see build stderr)"}
        except Exception as e:
            graph = {"ok": False, "detail": str(e)}

    # Report embeddings.json artifact state (final-review batch 2026-07-10).
    # The embeddings themselves were already refreshed in-process by the index
    # subprocess (scripts.build.embeddings runs at the end of
    # scripts.build.index, now BEFORE graph) — this block only *reports* what
    # landed; a missing artifact (semantic extra not installed, or the source
    # tree has zero indexable chunks) must never fail the rebuild.
    embeddings: dict = {}
    if proc.returncode == 0:
        try:
            from scripts.serve.retrieval import EMB_META_PATH

            if EMB_META_PATH.exists():
                m = json.loads(EMB_META_PATH.read_text())
                embeddings = {
                    "ok": True,
                    "built_at": m.get("built_at"),
                    "n_chunks": m.get("n_chunks"),
                    "incremental": m.get("incremental"),
                }
            else:
                embeddings = {
                    "ok": False,
                    "detail": (
                        "embeddings_meta.json missing — stage skipped (see build stderr; "
                        "install the semantic extra or run cli embed)"
                    ),
                }
        except Exception as e:
            embeddings = {"ok": False, "detail": str(e)}

    # Upsert a `## [date] index | ...` entry in vault _logs/log.md so the rebuild
    # shows up in the timeline — at most ONE index entry per day (same-day
    # rebuilds refresh it in place with a "Runs today: N" counter; log-noise
    # compaction 2026-07-11). Only log on success — failed rebuilds would
    # produce misleading "rebuild" entries in the timeline.
    # Safety net: `degraded` (PDF-less index while the vault has PDFs) should
    # no longer be reachable via this tool since md_only was removed, but the
    # CLI's --md-only flag can still produce it — keep surfacing it loudly.
    degraded = bool(stats.get("degraded"))
    if proc.returncode == 0 and pre_build_digest is not None:
        # Record the PRE-build fingerprint: if files changed mid-build, the
        # next call sees a different digest and rebuilds — no missed updates.
        try:
            write_saved_state(state_path, pre_build_digest)
        except Exception:  # noqa: BLE001 — state write must never fail the rebuild
            pass
    if proc.returncode == 0:
        try:
            wr.upsert_daily_log_entry(
                kind="index",
                title=(
                    f"RAG rebuild — {stats.get('n_files', '?')} files, {stats.get('n_chunks', '?')} chunks"
                    + (" — DEGRADED (md-only, PDFs excluded)" if degraded else "")
                ),
                body=(
                    f"Trigger: rebuild_index MCP tool (full). "
                    f"Elapsed: {elapsed:.1f}s. "
                    f"Mirror: {'refreshed' if mirror.get('ok') else 'REFRESH FAILED — run scripts.build.wiki_mirror by hand'}."
                    + (" WARNING: index contains 0 PDF files — follow with a full rebuild_index()." if degraded else "")
                ),
            )
        except Exception:
            pass

    payload = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "elapsed_s": round(elapsed, 1),
        "stats": stats,
        "stdout_tail": proc.stdout[-1500:] if proc.stdout else "",
        "stderr_tail": proc.stderr[-1500:] if proc.stderr else "",
        "mirror": mirror,
        "graph": graph,
        "embeddings": embeddings,
    }
    if degraded:
        payload["degraded"] = True
        payload["warning"] = (
            "The index contains 0 PDF files while the vault has PDFs (an md-only build "
            "leaked in, e.g. via the CLI's --md-only flag). search_wiki cannot see any "
            "PDF content until you run a full rebuild_index() (takes ~3s on a warm cache)."
        )
    return json.dumps(payload, indent=2, ensure_ascii=False)
