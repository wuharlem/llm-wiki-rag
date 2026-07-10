"""article_wikilink(): catalog -> maintained-article cross-link (concept-articles design §2c)."""

from __future__ import annotations

from scripts.build import wiki_mirror as wm


def test_article_wikilink_present(tmp_path):
    articles = tmp_path / wm._ARTICLES_RELPATH
    articles.mkdir(parents=True)
    (articles / "Guardrails__synthesis.md").write_text("# Guardrails — Synthesis\n")
    assert wm.article_wikilink(tmp_path, "Guardrails") == (
        "[[Guardrails__synthesis|Guardrails — maintained article]]"
    )


def test_article_wikilink_absent(tmp_path):
    assert wm.article_wikilink(tmp_path, "Guardrails") is None


def test_article_wikilink_slugifies_concept(tmp_path):
    """Concept names with spaces/punct must hit the slugified filename."""
    articles = tmp_path / wm._ARTICLES_RELPATH
    articles.mkdir(parents=True)
    slug = wm.slugify("Constitutional AI (RLAIF)")
    (articles / f"{slug}__synthesis.md").write_text("# x\n")
    link = wm.article_wikilink(tmp_path, "Constitutional AI (RLAIF)")
    assert link is not None and f"[[{slug}__synthesis|" in link
