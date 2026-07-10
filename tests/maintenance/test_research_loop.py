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
