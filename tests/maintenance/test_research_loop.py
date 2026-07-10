"""cli research: open_questions.md parsing contract + eligibility (research-loop spec §1–§2)."""

from __future__ import annotations

import datetime as dt

from scripts.maintenance import research_loop as rl

DOC = """---
title: Open Questions
type: meta
---

# Open Questions

Intro prose with the contract.

## [2026-07-10] thesis | Does deliberative alignment fix fake/shallow alignment — or inherit it?

Body paragraph one for the thesis entry.

**Researched:** 2026-07-03 — Early sweep found two candidates. — staged 2 source(s).
  - staged: https://arxiv.org/abs/2501.00001 → Fake_Alignment_abc12345.md
  - staged: https://example.com/post → Post_def67890.md

## [2026-07-09] gap | Cross-industry jailbreak-severity framework

Fresh gap entry, never researched.

## [2026-06-01] gap | **Resolved:** 2026-07-01 → Old question about eval decay

This one was resolved by a later ingest.

## [2026-05-20] methodology | Ancient methodology question

**Resolved:** 2026-06-30 → answered via saved query.
"""


def test_parse_entries_shapes():
    es = rl.parse_entries(DOC)
    assert [e.kind for e in es] == ["thesis", "gap", "gap", "methodology"]
    t = es[0]
    assert t.date == "2026-07-10"
    # Don't hand-compute the 60-char truncation — derive it and check shape.
    assert t.slug == rl.slugify_title(t.title)
    assert t.slug.startswith("does-deliberative-alignment") and len(t.slug) <= 60
    assert t.last_researched == "2026-07-03"
    assert t.staged == [
        ("https://arxiv.org/abs/2501.00001", "Fake_Alignment_abc12345.md"),
        ("https://example.com/post", "Post_def67890.md"),
    ]
    assert es[1].last_researched is None and es[1].staged == []


def test_resolved_both_conventions():
    es = rl.parse_entries(DOC)
    assert es[2].resolved is True  # Resolved in heading title
    assert es[3].resolved is True  # Resolved as first body line
    assert es[0].resolved is False


def test_eligibility_rules():
    es = rl.parse_entries(DOC)
    today = dt.date(2026, 7, 10)
    assert rl.is_eligible(es[1], today) is True  # never researched
    assert rl.is_eligible(es[0], today) is False  # researched 7 days ago
    assert rl.is_eligible(es[0], dt.date(2026, 8, 15)) is True  # >30d -> re-eligible
    assert rl.is_eligible(es[2], today) is False  # resolved
    assert rl.is_eligible(es[3], today) is False


def test_slug_truncation_and_kebab():
    assert rl.slugify_title("A B  c—d (e)") == "a-b-c-d-e"
    assert len(rl.slugify_title("x" * 200)) == 60


def test_list_json_on_tmp_vault(tmp_path, monkeypatch, capsys):
    (tmp_path / "open_questions.md").write_text(DOC)
    monkeypatch.setattr(rl, "vault_path", lambda: tmp_path)
    rc = rl.main(["list", "--json"])
    assert rc == 0
    import json

    out = json.loads(capsys.readouterr().out)
    assert len(out) == 4 and out[1]["eligible"] is True and out[2]["eligible"] is False


def test_parser_ignores_fenced_examples():
    doc = (
        DOC
        + """
## [2026-07-01] gap | Entry with fenced example

Body text.

```
## [2020-01-01] gap | NOT a real entry
  - staged: https://fake.example → Not_Real.md
```

Real trailing text.
"""
    )
    es = rl.parse_entries(doc)
    assert len(es) == 5  # the 4 originals + the one real new entry
    assert es[4].staged == []  # fenced staged line ignored


def test_list_eligible_only_empty_exit_zero(tmp_path, monkeypatch, capsys):
    (tmp_path / "open_questions.md").write_text(
        DOC.replace(
            "## [2026-07-09] gap | Cross-industry jailbreak-severity framework\n\nFresh gap entry, never researched.\n",
            "",
        )
    )
    monkeypatch.setattr(rl, "vault_path", lambda: tmp_path)
    monkeypatch.setattr(rl, "_today", lambda: dt.date(2026, 7, 10))
    rc = rl.main(["list", "--json", "--eligible-only"])
    assert rc == 0
    import json

    assert json.loads(capsys.readouterr().out) == []


def _tmp_vault(tmp_path, monkeypatch, doc=DOC):
    (tmp_path / "open_questions.md").write_text(doc)
    (tmp_path / "_add_by_me").mkdir()
    monkeypatch.setattr(rl, "vault_path", lambda: tmp_path)
    work = tmp_path / "work"
    (work / "02_logs").mkdir(parents=True)
    (work / "01_data").mkdir()
    monkeypatch.setattr(rl, "work_path", lambda: work)
    monkeypatch.setattr(rl, "_today", lambda: dt.date(2026, 7, 10))
    return tmp_path, work


def test_brief_creates_and_replaces_marker(tmp_path, monkeypatch):
    vault, _ = _tmp_vault(tmp_path, monkeypatch)
    slug = "cross-industry-jailbreak-severity-framework"
    assert rl.main(["brief", slug, "--text", "Two candidate surveys found."]) == 0
    text = (vault / "open_questions.md").read_text()
    assert "**Researched:** 2026-07-10 — Two candidate surveys found. — staged 0 source(s)." in text
    # idempotent replace
    assert rl.main(["brief", slug, "--text", "Revised brief."]) == 0
    text = (vault / "open_questions.md").read_text()
    assert text.count("**Researched:**") == 2  # this entry + the pre-existing thesis entry
    assert "Revised brief." in text and "Two candidate surveys found." not in text
    # round-trip: file still parses, other entries untouched
    es = rl.parse_entries(text)
    assert [e.kind for e in es] == ["thesis", "gap", "gap", "methodology"]


def test_stage_dedup_against_notion_sources(tmp_path, monkeypatch, capsys):
    vault, work = _tmp_vault(tmp_path, monkeypatch)
    (work / "01_data" / "notion_sources.csv").write_text("title,url\nSome Paper,https://arxiv.org/abs/2501.00042\n")
    rc = rl.main(
        ["stage", "cross-industry-jailbreak-severity-framework", "https://arxiv.org/abs/2501.00042?utm_source=x"]
    )
    assert rc == 3
    assert "already ingested" in capsys.readouterr().err


def test_stage_dedup_against_staged_and_nominated(tmp_path, monkeypatch, capsys):
    vault, work = _tmp_vault(tmp_path, monkeypatch)
    (vault / "_add_by_me" / "Old_abc.md").write_text(
        '---\ntitle: "Old"\nsource_url: https://example.com/staged-one\n---\n'
    )
    rc = rl.main(["stage", "cross-industry-jailbreak-severity-framework", "https://example.com/staged-one"])
    assert rc == 3 and "already staged" in capsys.readouterr().err
    # nominated under ANOTHER question (the thesis entry's staged line)
    rc = rl.main(["stage", "cross-industry-jailbreak-severity-framework", "https://example.com/post"])
    assert rc == 3 and "already nominated" in capsys.readouterr().err


def test_stage_caps(tmp_path, monkeypatch, capsys):
    vault, work = _tmp_vault(tmp_path, monkeypatch)
    # per-question cap: thesis entry already has 2 staged; lower cap to 2 to hit it
    monkeypatch.setattr(rl, "MAX_STAGED_PER_QUESTION", 2)
    thesis_slug = rl.parse_entries(DOC)[0].slug  # derive, don't hand-compute
    rc = rl.main(["stage", thesis_slug, "https://example.com/new-one"])
    assert rc == 4 and "per-question cap" in capsys.readouterr().err
    # per-run cap via the runs csv
    monkeypatch.setattr(rl, "MAX_STAGED_PER_RUN", 1)
    runs = rl.runs_csv_path()
    runs.write_text("run_id,timestamp,slug,url,outcome\n2026-07-10,t,x,https://a,staged\n")
    rc = rl.main(["stage", "cross-industry-jailbreak-severity-framework", "https://example.com/fresh"])
    assert rc == 4 and "per-run cap" in capsys.readouterr().err


def test_stage_success_records_everything(tmp_path, monkeypatch):
    vault, work = _tmp_vault(tmp_path, monkeypatch)

    def fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = "OK handler=web file=Fresh_1234abcd.md\n"
            stderr = ""

        # simulate stage_candidate writing the file
        (vault / "_add_by_me" / "Fresh_1234abcd.md").write_text(
            '---\ntitle: "Fresh"\nsource_url: https://example.com/fresh\n---\n'
        )
        return R()

    monkeypatch.setattr(rl.subprocess, "run", fake_run)
    slug = "cross-industry-jailbreak-severity-framework"
    rc = rl.main(["stage", slug, "https://example.com/fresh", "--title", "Fresh"])
    assert rc == 0
    text = (vault / "open_questions.md").read_text()
    assert "  - staged: https://example.com/fresh → Fresh_1234abcd.md" in text
    assert "staged 1 source(s)." in text  # marker auto-created with empty brief
    ledger = rl.runs_csv_path().read_text()
    assert "2026-07-10" in ledger and "staged" in ledger
    es = rl.parse_entries(text)
    assert rl._find(es, slug).staged == [("https://example.com/fresh", "Fresh_1234abcd.md")]


def test_brief_survives_fenced_heading_in_body(tmp_path, monkeypatch):
    doc = (
        DOC
        + """
## [2026-07-01] gap | Entry with fenced example

Body text.

```
## [2020-01-01] gap | NOT a real entry
```

Trailing text.
"""
    )
    vault, _ = _tmp_vault(tmp_path, monkeypatch, doc=doc)
    slug = rl.slugify_title("Entry with fenced example")
    assert rl.main(["brief", slug, "--text", "Marker must land outside the fence."]) == 0
    text = (vault / "open_questions.md").read_text()
    es = rl.parse_entries(text)
    e = next(x for x in es if x.slug == slug)
    assert e.brief == "Marker must land outside the fence."  # visible after round-trip
    assert e.last_researched == "2026-07-10"
    # fence intact: still an even number of fence delimiters in the entry body
    assert text.count("```") % 2 == 0


def test_hits_query_skips_fenced_body(tmp_path, monkeypatch, capsys):
    doc = (
        DOC
        + """
## [2026-07-02] gap | Fence-first entry

```
fenced example text that must not become the query
```

Real prose line about interpretability probes.
"""
    )
    _tmp_vault(tmp_path, monkeypatch, doc=doc)
    from scripts.serve import retrieval as wr

    captured = {}

    def fake_search(query, **kw):
        captured["q"] = query
        return []

    monkeypatch.setattr(wr, "search", fake_search)
    rc = rl.main(["hits", rl.slugify_title("Fence-first entry")])
    assert rc == 0
    assert "fenced example text" not in captured["q"]
    assert "Real prose line about interpretability probes" in captured["q"]


def test_hits_prints_corpus_evidence(tmp_path, monkeypatch, capsys):
    _tmp_vault(tmp_path, monkeypatch)
    from scripts.serve import retrieval as wr

    chunks = [
        {
            "file_id": "aaaaaaaaaaaa",
            "chunk_id": "c0000",
            "relpath": "01/A.md",
            "title": "Jailbreak severity frameworks",
            "category": "01",
            "subcategory": "",
            "heading_path": "",
            "tokens": 5,
            "tags": [],
            "concepts": [],
            "text": "cross-industry jailbreak severity framework adoption",
        }
    ]
    monkeypatch.setattr(wr._ctx, "chunks", chunks)
    monkeypatch.setattr(wr._ctx, "chunks_by_file", {"aaaaaaaaaaaa": chunks})
    rc = rl.main(["hits", "cross-industry-jailbreak-severity-framework", "--k", "3"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Jailbreak severity frameworks" in out and "01/A.md" in out
