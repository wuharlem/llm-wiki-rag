"""fetch.py's pre-fetch guard: a URL whose hash suffix (or arxiv ID) already
appears in a vault filename is skipped before any HTTP request, so slug-rename
refetches can't reintroduce byte-identical copies (the `_int` incident).
`--force` bypasses the vault scan but still dedupes within a run."""

from __future__ import annotations

import csv
import sys

import pytest

pytest.importorskip("requests")
pytest.importorskip("trafilatura")

from scripts.ingest import fetch as fx  # noqa: E402


# ---------------------------------------------------------------------------
# Suffix / ID extraction
# ---------------------------------------------------------------------------
def test_hash_suffix_regex_end_anchored():
    """arxiv fallback names carry TWO 8-hex tokens (arxiv_id() falls back to
    short_hash in the slug); only the trailing one is the filename hash."""
    assert fx._HASH_SUFFIX_RE.search("arxiv_deadbeef_ab12cd34.pdf").group(1) == "ab12cd34"
    assert fx._HASH_SUFFIX_RE.search("note_deadbeef.md").group(1) == "deadbeef"
    assert fx._HASH_SUFFIX_RE.search("plain.md") is None
    assert fx._HASH_SUFFIX_RE.search("2301.12345.pdf") is None


def test_collect_fetched_markers(tmp_path):
    vault = tmp_path / "vault"
    for rel in [
        "01_R/paper_ab12cd34.pdf",
        "Sources/_inbox/note_deadbeef.md",
        "_trash/2026/gone_cafeb0de.pdf",
        ".obsidian/x_12345678.md",
        "01_R/plain.md",
    ]:
        p = vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    hashes, _ids = fx.collect_fetched_markers(vault)
    assert hashes == {"ab12cd34", "deadbeef"}


def test_collect_fetched_markers_arxiv_ids(tmp_path):
    """Both fetched arxiv names and hand-dropped raw arxiv PDFs register IDs."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "arxiv_2301.12345_ab12cd34.pdf").write_text("x")
    (vault / "2401.00001v2.pdf").write_text("x")
    hashes, ids = fx.collect_fetched_markers(vault)
    assert ids >= {"2301.12345", "2401.00001"}
    assert hashes == {"ab12cd34"}


def test_collect_fetched_markers_missing_vault(tmp_path):
    hashes, ids = fx.collect_fetched_markers(tmp_path / "nope")
    assert hashes == set() and ids == set()


# ---------------------------------------------------------------------------
# fetch_one guard
# ---------------------------------------------------------------------------
def _fail_writer(*a, **kw):
    pytest.fail("writer called despite guard — an HTTP fetch would have fired")


def test_fetch_one_skips_existing_hash(monkeypatch):
    monkeypatch.setattr(fx, "write_web_md", _fail_writer)
    url = "https://example.org/some-article"
    row = {"url": url, "handler": "web"}
    out = fx.fetch_one(row, {fx.short_hash(url)}, set())
    assert out["status"] == "skipped"
    assert "already fetched" in out["info"]
    assert out["filename"] == ""


def test_fetch_one_arxiv_guard_uses_transformed_url(monkeypatch):
    """The filename hash is short_hash(arxiv_pdf_url(url)), not the /abs/ URL —
    the guard must check the same value."""
    monkeypatch.setattr(fx, "write_pdf", _fail_writer)
    row = {"url": "https://arxiv.org/abs/2301.12345", "handler": "arxiv"}
    seen = {fx.short_hash("https://arxiv.org/pdf/2301.12345.pdf")}
    out = fx.fetch_one(row, seen, set())
    assert out["status"] == "skipped"


def test_fetch_one_arxiv_guard_matches_raw_id(monkeypatch):
    """A hand-dropped raw arxiv PDF (no hash suffix) still blocks a refetch."""
    monkeypatch.setattr(fx, "write_pdf", _fail_writer)
    row = {"url": "https://arxiv.org/abs/2401.00001v2", "handler": "arxiv"}
    out = fx.fetch_one(row, set(), {"2401.00001"})
    assert out["status"] == "skipped"


def test_fetch_one_claims_hash_within_run(monkeypatch):
    calls = []

    def stub(url, dest_dir, name_hint):
        calls.append(url)
        return "f_x.pdf", "10 bytes"

    monkeypatch.setattr(fx, "write_pdf", stub)
    row = {"url": "https://example.org/paper.pdf", "handler": "pdf"}
    seen_hashes, seen_ids = set(), set()
    first = fx.fetch_one(row, seen_hashes, seen_ids)
    second = fx.fetch_one(row, seen_hashes, seen_ids)
    assert first["status"] == "ok"
    assert second["status"] == "skipped"
    assert len(calls) == 1


def test_fetch_one_none_sets_disable_guard(monkeypatch):
    monkeypatch.setattr(fx, "write_web_md", lambda url, dest_dir: ("f.md", "1 chars"))
    out = fx.fetch_one({"url": "https://example.org/a", "handler": "web"})
    assert out["status"] == "ok"


# ---------------------------------------------------------------------------
# main() integration: guard on by default, --force bypasses
# ---------------------------------------------------------------------------
def test_main_guard_and_force(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    inbox = vault / "Sources" / "_inbox"
    logs = tmp_path / "logs"
    logs.mkdir()
    url_old = "https://example.org/already-have"
    url_new = "https://example.org/brand-new"
    seeded = vault / "01_Cat" / f"old_{fx.short_hash(url_old)}.md"
    seeded.parent.mkdir(parents=True)
    seeded.write_text("curated copy", encoding="utf-8")

    dedup_csv = tmp_path / "urls_dedup.csv"
    dedup_csv.write_text(f"url,handler\n{url_old},web\n{url_new},web\n", encoding="utf-8")
    log_csv = logs / "fetch_log.csv"

    def stub(url, dest_dir):
        fname = f"stub_{fx.short_hash(url)}.md"
        (dest_dir / fname).write_text("stub", encoding="utf-8")
        return fname, "4 chars"

    monkeypatch.setattr(fx, "VAULT", vault)
    monkeypatch.setattr(fx, "INBOX", inbox)
    monkeypatch.setattr(fx, "DEDUP_CSV", dedup_csv)
    monkeypatch.setattr(fx, "LOG_CSV", log_csv)
    monkeypatch.setattr(fx, "SOURCES_CSV", tmp_path / "no_sources.csv")
    monkeypatch.setattr(fx, "write_web_md", stub)

    monkeypatch.setattr(sys, "argv", ["fetch"])
    fx.main()
    with log_csv.open(newline="") as f:
        run1 = {r["url"]: r["status"] for r in csv.DictReader(f)}
    assert run1[url_old] == "skipped"
    assert run1[url_new] == "ok"

    monkeypatch.setattr(sys, "argv", ["fetch", "--force"])
    fx.main()
    with log_csv.open(newline="") as f:
        rows = list(csv.DictReader(f))
    run2 = {r["url"]: r["status"] for r in rows[2:]}
    assert run2 == {url_old: "ok", url_new: "ok"}
