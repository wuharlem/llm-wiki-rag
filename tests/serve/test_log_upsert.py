"""
test_log_upsert — upsert_daily_log_entry keeps at most one <kind> entry per day.

Pins the log-noise-compaction contract (2026-07-11): same-day rebuilds
rewrite the day's `index` entry in place with a "Runs today: N" counter
instead of flooding log.md with one heading per rebuild; other kinds and
other days still append normally.
"""

from __future__ import annotations

import datetime

import pytest

from scripts.serve import retrieval as wr

TODAY = datetime.date.today().isoformat()


@pytest.fixture
def tmp_vault(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(wr, "VAULT_PATH", vault)
    return vault


def _log_text(vault) -> str:
    return wr._vault_log_path().read_text(encoding="utf-8")


def test_first_upsert_falls_back_to_append(tmp_vault):
    path = wr.upsert_daily_log_entry(kind="index", title="rebuild one", body="Trigger: test.")
    assert path == tmp_vault / "_logs" / "log.md"  # pin the physical location once
    text = _log_text(tmp_vault)
    assert text.count(f"## [{TODAY}] index |") == 1
    assert "rebuild one" in text


def test_same_day_upsert_replaces_and_counts(tmp_vault):
    wr.upsert_daily_log_entry(kind="index", title="rebuild one", body="Trigger: a.")
    wr.upsert_daily_log_entry(kind="index", title="rebuild two", body="Trigger: b.")
    text = _log_text(tmp_vault)
    # Still exactly one index heading for today; latest title/body won.
    assert text.count(f"## [{TODAY}] index |") == 1
    assert "rebuild two" in text and "rebuild one" not in text
    assert "Runs today: 2." in text

    wr.upsert_daily_log_entry(kind="index", title="rebuild three", body="Trigger: c.")
    text = _log_text(tmp_vault)
    assert text.count(f"## [{TODAY}] index |") == 1
    assert "Runs today: 3." in text


def test_other_kinds_still_append_separately(tmp_vault):
    wr.upsert_daily_log_entry(kind="index", title="rebuild", body="Trigger: a.")
    wr.upsert_daily_log_entry(kind="audit", title="audit pass", body="")
    text = _log_text(tmp_vault)
    assert text.count(f"## [{TODAY}] index |") == 1
    assert text.count(f"## [{TODAY}] audit |") == 1
    # The index entry survived the audit upsert untouched.
    assert "rebuild" in text and "audit pass" in text


def test_missing_vault_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(wr, "VAULT_PATH", tmp_path / "nope")
    assert wr.upsert_daily_log_entry(kind="index", title="x") is None


def test_existing_older_entries_are_preserved(tmp_vault):
    """An upsert must only touch TODAY's entry of its kind — a same-kind
    entry under an older date stays intact."""
    wr.upsert_daily_log_entry(kind="index", title="today's rebuild", body="Trigger: a.")
    log_path = wr._vault_log_path()
    text = log_path.read_text(encoding="utf-8")
    old_entry = "## [2020-01-01] index | ancient rebuild\n\nOld body.\n\n"
    log_path.write_text(text + old_entry, encoding="utf-8")

    wr.upsert_daily_log_entry(kind="index", title="today again", body="Trigger: b.")
    text = _log_text(tmp_vault)
    assert "ancient rebuild" in text and "Old body." in text
    assert text.count("] index |") == 2  # one today, one ancient
    assert "Runs today: 2." in text


def test_legacy_root_log_is_adopted(tmp_vault):
    """A vault synced to this code without the manual file move (2026-07-16
    `_logs/` relocation): the root log.md is MOVED into `_logs/` on first
    write — history is never forked into a fresh bootstrap file."""
    legacy = tmp_vault / "log.md"
    legacy.write_text(
        wr._LOG_BOOTSTRAP_HEADER + "## [2020-01-01] ingest | ancient entry\n\nOld body.\n\n",
        encoding="utf-8",
    )
    wr.upsert_daily_log_entry(kind="index", title="first post-move rebuild", body="Trigger: a.")
    assert not legacy.exists()
    text = _log_text(tmp_vault)
    assert "ancient entry" in text and "Old body." in text
    assert text.count(f"## [{TODAY}] index |") == 1


def test_same_day_invariant_survives_migration(tmp_vault):
    """A today-entry written to the legacy root file (e.g. by a pre-restart
    server on the old code) is seen by the upsert after adoption — the
    one-index-entry-per-day invariant holds across the move."""
    legacy = tmp_vault / "log.md"
    legacy.write_text(
        wr._LOG_BOOTSTRAP_HEADER + f"## [{TODAY}] index | pre-move rebuild\n\nTrigger: old.\n\n",
        encoding="utf-8",
    )
    wr.upsert_daily_log_entry(kind="index", title="post-move rebuild", body="Trigger: new.")
    text = _log_text(tmp_vault)
    assert text.count(f"## [{TODAY}] index |") == 1
    assert "Runs today: 2." in text


def test_stray_root_log_left_for_manual_merge(tmp_vault):
    """When `_logs/log.md` already exists, a stray root log.md (recreated by
    a not-yet-restarted server) is left alone — renaming over the live log
    would lose entries; the merge is manual by design."""
    wr.append_log_entry(kind="ingest", title="already migrated")
    stray = tmp_vault / "log.md"
    stray.write_text("stray root copy\n", encoding="utf-8")
    wr.append_log_entry(kind="ingest", title="second entry")
    assert stray.read_text(encoding="utf-8") == "stray root copy\n"
    assert "second entry" in _log_text(tmp_vault)
