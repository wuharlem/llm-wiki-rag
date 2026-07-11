"""
test_rebuild_debounce — the debounce and payload-assembly branches of the
`rebuild_index` MCP tool (serve/mcp_tools/admin.py).

The real build runs in a subprocess, so these tests fake `subprocess.run`
and the source-state helpers; what's pinned is the tool's *decision logic*:
when it skips, when it rebuilds, what it writes, and what the payload
promises downstream agents (mirror / graph / embeddings blocks, skip
payload shape, the rebuild_timeout envelope).

Everything vault- and repo-mutating is monkeypatched — these tests never
touch the real state file, log.md, or caches.
"""

from __future__ import annotations

import json
import subprocess
import types

import pytest

from scripts.serve import mcp_server as ws
from scripts.serve import retrieval as wr
from scripts.wiki_lib import source_state as ss

DIGEST = "d" * 64


class FakeRun:
    """Stand-in for subprocess.run recording each invocation.

    `returncodes` maps a substring of the command (e.g. "scripts.build.index")
    to the returncode the fake process should report.
    """

    def __init__(self, returncodes: dict[str, int] | None = None, raise_timeout: bool = False):
        self.returncodes = returncodes or {}
        self.raise_timeout = raise_timeout
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        joined = " ".join(cmd)
        if self.raise_timeout and "scripts.build.index" in joined:
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 900))
        rc = next((code for key, code in self.returncodes.items() if key in joined), 0)
        return types.SimpleNamespace(returncode=rc, stdout=f"ran {joined}", stderr="")


@pytest.fixture
def rebuild_env(monkeypatch, tmp_path):
    """Hermetic harness for rebuild_index: fake fingerprints, fake stats,
    fake subprocesses, captured state writes and log entries."""
    env = types.SimpleNamespace(
        digest=DIGEST,
        saved=DIGEST,
        stats={"n_chunks": 100, "n_files": 10, "degraded": False},
        state_writes=[],
        log_entries=[],
        run=FakeRun(),
    )

    monkeypatch.setattr(ss, "compute_source_state", lambda vault: env.digest)
    monkeypatch.setattr(ss, "read_saved_state", lambda path: env.saved)
    monkeypatch.setattr(ss, "write_saved_state", lambda path, digest: env.state_writes.append(digest))
    monkeypatch.setattr(wr, "index_stats", lambda: dict(env.stats))
    monkeypatch.setattr(wr, "invalidate_caches", lambda: None)
    # The success-log call is transitioning append_log_entry ->
    # upsert_daily_log_entry (log-noise compaction, 2026-07-11); capture
    # whichever the tool calls so the pin survives the rename landing.
    monkeypatch.setattr(wr, "append_log_entry", lambda **kw: env.log_entries.append(kw), raising=False)
    monkeypatch.setattr(wr, "upsert_daily_log_entry", lambda **kw: env.log_entries.append(kw), raising=False)
    monkeypatch.setattr(subprocess, "run", env.run)
    # Point the artifact-report paths at tmp so the blocks report "missing"
    # unless a test writes them.
    monkeypatch.setattr(wr, "GRAPH_PATH", tmp_path / "graph.json")
    monkeypatch.setattr(wr, "EMB_META_PATH", tmp_path / "embeddings_meta.json")
    return env


def _call(**kwargs) -> dict:
    return json.loads(ws.rebuild_index(ws.RebuildIndexInput(**kwargs)))


# ---------------------------------------------------------------------------
# Debounce decision
# ---------------------------------------------------------------------------


def test_skip_when_sources_unchanged(rebuild_env):
    payload = _call()
    assert payload["ok"] is True
    assert payload["skipped"] is True
    assert payload["reason"] == "sources_unchanged"
    assert payload["stats"]["n_chunks"] == 100
    assert rebuild_env.run.calls == []  # no subprocess, no state write, no log
    assert rebuild_env.state_writes == []
    assert rebuild_env.log_entries == []


def test_force_bypasses_debounce(rebuild_env):
    payload = _call(force=True)
    assert payload["ok"] is True
    assert "skipped" not in payload
    assert any("scripts.build.index" in " ".join(c) for c in rebuild_env.run.calls)
    # The PRE-build fingerprint is recorded so mid-build edits still rebuild next time.
    assert rebuild_env.state_writes == [DIGEST]


def test_digest_mismatch_rebuilds(rebuild_env):
    rebuild_env.saved = "stale-digest"
    payload = _call()
    assert "skipped" not in payload
    assert any("scripts.build.index" in " ".join(c) for c in rebuild_env.run.calls)


def test_no_skip_when_index_degraded(rebuild_env):
    """Matching digests must NOT debounce over a degraded index — the skip is
    only safe when the existing index is trustworthy."""
    rebuild_env.stats = {"n_chunks": 100, "degraded": True}
    payload = _call()
    assert "skipped" not in payload


def test_no_skip_when_index_empty(rebuild_env):
    rebuild_env.stats = {"n_chunks": 0}
    payload = _call()
    assert "skipped" not in payload


def test_fingerprint_failure_still_rebuilds(rebuild_env, monkeypatch):
    """A fingerprint crash must never block a rebuild — and must not record
    state afterwards (there is nothing trustworthy to record)."""

    def boom(vault):
        raise RuntimeError("stat storm")

    monkeypatch.setattr(ss, "compute_source_state", boom)
    payload = _call()
    assert payload["ok"] is True
    assert "skipped" not in payload
    assert rebuild_env.state_writes == []


# ---------------------------------------------------------------------------
# Payload assembly on a real (faked) rebuild
# ---------------------------------------------------------------------------


def test_success_payload_reports_all_blocks(rebuild_env, tmp_path):
    (tmp_path / "graph.json").write_text(json.dumps({"built_at": "2026-07-11", "n_edges": 42, "n_communities": 7}))
    (tmp_path / "embeddings_meta.json").write_text(
        json.dumps({"built_at": "2026-07-11", "n_chunks": 100, "incremental": True})
    )
    payload = _call(force=True)

    assert payload["ok"] is True
    assert payload["mirror"]["ok"] is True
    assert payload["graph"] == {"ok": True, "built_at": "2026-07-11", "n_edges": 42, "n_communities": 7}
    assert payload["embeddings"]["ok"] is True
    assert payload["embeddings"]["incremental"] is True
    # Mirror subprocess ran after the index subprocess.
    joined = [" ".join(c) for c in rebuild_env.run.calls]
    assert any("scripts.build.index" in c for c in joined)
    assert any("scripts.build.wiki_mirror" in c for c in joined)
    # Success is logged exactly once, as kind="index".
    assert len(rebuild_env.log_entries) == 1
    assert rebuild_env.log_entries[0]["kind"] == "index"


def test_missing_artifacts_reported_but_not_fatal(rebuild_env):
    """Absent graph.json / embeddings_meta.json (e.g. semantic extra not
    installed) degrade to ok=False blocks — never a failed rebuild."""
    payload = _call(force=True)
    assert payload["ok"] is True
    assert payload["graph"]["ok"] is False
    assert payload["embeddings"]["ok"] is False


def test_mirror_failure_never_fails_rebuild(rebuild_env):
    rebuild_env.run.returncodes = {"scripts.build.wiki_mirror": 1}
    payload = _call(force=True)
    assert payload["ok"] is True
    assert payload["mirror"]["ok"] is False
    # The log line flags the failed mirror so an agent runs it by hand.
    assert "REFRESH FAILED" in rebuild_env.log_entries[0]["body"]


def test_failed_build_writes_nothing(rebuild_env):
    rebuild_env.run.returncodes = {"scripts.build.index": 3}
    payload = _call(force=True)
    assert payload["ok"] is False
    assert payload["returncode"] == 3
    assert rebuild_env.state_writes == []  # a failed build must not update the debounce state
    assert rebuild_env.log_entries == []  # ...or log a misleading "rebuild" entry
    assert payload["mirror"] == {}  # mirror is not attempted


def test_timeout_returns_canonical_envelope(rebuild_env):
    rebuild_env.run.raise_timeout = True
    payload = _call(force=True)
    assert set(payload.keys()) == {"ok", "error", "detail"}
    assert payload["ok"] is False
    assert payload["error"] == "rebuild_timeout"
    assert rebuild_env.state_writes == []
