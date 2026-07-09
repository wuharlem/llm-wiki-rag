"""
test_emit_manifest — pin the manifest CSV emit helper's contract.

Locks in the canonical 17-column header (CLAUDE.md §3), special-character
sanitization, list-field pipe joining, empty-input behavior, and the
fallback-row path on writer failure.
"""

from __future__ import annotations

import csv

from scripts.build import index as bi

CANONICAL_HEADER = [
    "file_id",
    "type",
    "category",
    "subcategory",
    "title",
    "n_chunks",
    "n_tokens",
    "n_pages",
    "tags",
    "concepts",
    "risk_category",
    "source_type",
    "author",
    "published",
    "source_url",
    "summary",
    "relpath",
]


def _make_entry(**overrides) -> bi.FileEntry:
    """Construct a FileEntry with sane defaults; override fields via kwargs."""
    field_values = {
        "tags": overrides.pop("tags", []),
        "concepts": overrides.pop("concepts", []),
        "risk_category": overrides.pop("risk_category", []),
        "source_type": overrides.pop("source_type", ""),
        "author": overrides.pop("author", ""),
        "published": overrides.pop("published", ""),
        "source_url": overrides.pop("source_url", ""),
    }
    defaults = dict(
        file_id="f1",
        relpath="01_Risks-and-Failure-Modes/test.md",
        type="md",
        title="Test",
        folder="01_Risks-and-Failure-Modes",
        category="01_Risks-and-Failure-Modes",
        subcategory="01a",
        description="",
        summary="",
        fields=field_values,
        n_pages=0,
        n_chunks=1,
        n_tokens=10,
        body_sha1="",
        chunks=[],
    )
    defaults.update(overrides)
    return bi.FileEntry(**defaults)


def test_emit_manifest_csv_writes_canonical_header(tmp_path):
    out = tmp_path / "m.csv"
    bi._emit_manifest_csv([_make_entry()], out)
    rows = list(csv.reader(out.read_text(encoding="utf-8").splitlines()))
    assert rows[0] == CANONICAL_HEADER


def test_emit_manifest_csv_handles_special_chars_in_title(tmp_path):
    out = tmp_path / "m.csv"
    entry = _make_entry(title='A: B\x00\nC"D')
    bi._emit_manifest_csv([entry], out)
    rows = list(csv.reader(out.read_text(encoding="utf-8").splitlines()))
    title_cell = rows[1][CANONICAL_HEADER.index("title")]
    assert "\x00" not in title_cell, "null byte must be stripped"
    assert "\n" not in title_cell, "newline must be collapsed"


def test_emit_manifest_csv_pipe_joins_list_fields(tmp_path):
    out = tmp_path / "m.csv"
    entry = _make_entry(tags=["a", "b"], concepts=["c", "d"], risk_category=["e"])
    bi._emit_manifest_csv([entry], out)
    rows = list(csv.reader(out.read_text(encoding="utf-8").splitlines()))
    row = rows[1]
    assert row[CANONICAL_HEADER.index("tags")] == "a|b"
    assert row[CANONICAL_HEADER.index("concepts")] == "c|d"
    assert row[CANONICAL_HEADER.index("risk_category")] == "e"


def test_emit_manifest_csv_empty_entries_writes_only_header(tmp_path):
    out = tmp_path / "m.csv"
    bi._emit_manifest_csv([], out)
    rows = list(csv.reader(out.read_text(encoding="utf-8").splitlines()))
    assert len(rows) == 1
    assert rows[0] == CANONICAL_HEADER


def test_emit_manifest_csv_fallback_row_on_writer_failure(tmp_path, capsys, monkeypatch):
    out = tmp_path / "m.csv"
    entry = _make_entry()

    state = {"calls": 0}
    real_writer_factory = csv.writer

    class FlakyWriter:
        def __init__(self, inner):
            self._inner = inner

        def writerow(self, row):
            state["calls"] += 1
            if state["calls"] == 2:
                raise ValueError("boom")
            return self._inner.writerow(row)

    def flaky_factory(*args, **kwargs):
        return FlakyWriter(real_writer_factory(*args, **kwargs))

    monkeypatch.setattr(bi.csv, "writer", flaky_factory)
    bi._emit_manifest_csv([entry], out)
    captured = capsys.readouterr()
    assert "CSV-FAIL" in captured.out, f"expected CSV-FAIL in stdout, got: {captured.out}"
    rows = list(csv.reader(out.read_text(encoding="utf-8").splitlines()))
    # Header + one fallback data row.
    assert len(rows) == 2
    assert rows[1][0] == "f1", "fallback row should preserve file_id"
