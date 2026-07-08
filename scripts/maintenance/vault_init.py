"""vault-init — render templates/vault/ PROCESS-doc skeletons into the vault.

Bootstraps a new adopter's vault with the operational docs the pipeline
assumes (ingest / query / health-check workflows), with the vocabulary
section GENERATED from wiki_schema.yml so doc and runtime can't drift
(CLAUDE.md §1). Invoked via the frozen facade:

    python -m scripts.cli vault-init                   # write skeletons (skip existing)
    python -m scripts.cli vault-init --force           # overwrite existing
    python -m scripts.cli vault-init --refresh-vocab   # resync only the generated
                                                       # vocab block in PROCESS_NEW_FILE.md

Never deletes; never overwrites without --force (CLAUDE.md §6 philosophy).
The generated block must stay parseable by check_vocab_sync.py's
_section/_table_first_column/_backticked — tests/maintenance/test_vault_init.py
pins that round-trip.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from scripts.wiki_lib.locations import vault_path
from scripts.wiki_lib.schema import WikiSchema, get_schema, mcp_server_name

# Templates ship with the code, so resolve them file-relative (like
# schema.SCHEMA_PATH), not via work_path() — WIKI_WORK may point elsewhere.
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "vault"

_BEGIN = "<!-- BEGIN GENERATED VOCAB"
_END = "<!-- END GENERATED VOCAB -->"
_BLOCK_RE = re.compile(re.escape(_BEGIN) + r".*?" + re.escape(_END), re.DOTALL)

_NO_TRIGGERS = "(curatorial — assigned by hand, never auto-suggested)"


def _axis_heading(axis_name: str) -> str:
    """`risk_category` -> `Risk Categories` — matches the heading form
    check_vocab_sync.py parses in the live vault doc."""
    words = [w.capitalize() for w in axis_name.split("_")]
    last = words[-1]
    if last.endswith("y"):
        words[-1] = last[:-1] + "ies"
    elif not last.endswith("s"):
        words[-1] = last + "s"
    return " ".join(words)


def render_vocab_block(schema: WikiSchema) -> str:
    """The generated Step-2 vocabulary section of PROCESS_NEW_FILE.md.

    Format contract: check_vocab_sync.py reads concepts and axis values from
    the FIRST table column and tags as BACKTICKED tokens — keep prose inside
    these sections free of backticks and don't add extra tables.
    """
    lines = [
        f"{_BEGIN} — source: wiki_schema.yml — do not hand-edit; refresh with"
        " `python -m scripts.cli vault-init --refresh-vocab` -->",
        "",
        "### Wiki Concepts",
        "",
        "| Concept | Covers |",
        "|---|---|",
    ]
    for name, triggers in schema.vocabulary.concepts.items():
        covers = ", ".join(triggers) if triggers else _NO_TRIGGERS
        lines.append(f"| {name} | {covers} |")
    lines += ["", "### Tag Vocabulary", ""]
    lines.append(", ".join(f"`{tag}`" for tag in schema.vocabulary.tags))
    for axis_name, axis in schema.vocabulary.categorical_axes.items():
        lines += ["", f"### {_axis_heading(axis_name)}", "", "| Value | Scope |", "|---|---|"]
        for value, triggers in axis.values.items():
            scope = ", ".join(triggers) if triggers else _NO_TRIGGERS
            lines.append(f"| {value} | {scope} |")
    lines += ["", _END]
    return "\n".join(lines)


def render_frontmatter_example(schema: WikiSchema) -> str:
    """A fenced YAML example listing every schema frontmatter field with a
    type-appropriate placeholder value."""
    lines = ["```yaml", "---"]
    for field in schema.frontmatter.fields:
        if field.type in ("tag_list", "concept_list", "categorical_list"):
            source = {
                "tag_list": "the Tag Vocabulary below",
                "concept_list": "the Wiki Concepts table below",
            }.get(field.type, f"the {_axis_heading(field.vocab_key or field.name)} table below")
            lines.append(f"{field.name}:")
            lines.append(f"- <value from {source}>")
        elif field.type == "enum":
            lines.append(f"{field.name}: <one of: {' | '.join(field.values or [])}>")
        elif field.type == "date_string":
            lines.append(f"{field.name}: <YYYY-MM-DD, or null if unknown>")
        elif field.type == "url":
            lines.append(f"{field.name}: <source URL>")
        else:  # string
            lines.append(f"{field.name}: <free text>")
    lines += ["---", "```"]
    return "\n".join(lines)


def _placeholders(schema: WikiSchema) -> dict[str, str]:
    return {
        "{{WIKI_NAME}}": schema.wiki.name,
        "{{WIKI_SLUG}}": schema.wiki.slug,
        "{{MCP_SERVER_NAME}}": mcp_server_name(schema),
        "{{VAULT_PATH}}": str(vault_path()),
        "{{FRONTMATTER_EXAMPLE}}": render_frontmatter_example(schema),
        "{{GENERATED_VOCAB_BLOCK}}": render_vocab_block(schema),
    }


def render_template(template_path: Path, schema: WikiSchema) -> str:
    text = template_path.read_text(encoding="utf-8")
    for key, value in _placeholders(schema).items():
        text = text.replace(key, value)
    return text


def _refresh_vocab(schema: WikiSchema, vault: Path) -> int:
    target = vault / "PROCESS_NEW_FILE.md"
    if not target.exists():
        print(f"FAIL: {target} not found (set WIKI_VAULT?)", file=sys.stderr)
        return 1
    text = target.read_text(encoding="utf-8")
    if not _BLOCK_RE.search(text):
        print(
            f"FAIL: no GENERATED VOCAB markers in {target} — cannot refresh. "
            "Re-render with `vault-init --force`, or paste the block markers in first.",
            file=sys.stderr,
        )
        return 1
    # Lambda replacement: the block may contain backslashes; keep re.sub literal.
    target.write_text(_BLOCK_RE.sub(lambda _m: render_vocab_block(schema), text), encoding="utf-8")
    print(f"refreshed vocab block in {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render templates/vault/ PROCESS-doc skeletons into the vault (WIKI_VAULT)."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--force", action="store_true", help="overwrite existing vault files")
    group.add_argument(
        "--refresh-vocab",
        action="store_true",
        help="only regenerate the GENERATED VOCAB block inside the vault's existing PROCESS_NEW_FILE.md",
    )
    args = parser.parse_args(argv)

    schema = get_schema()
    vault = vault_path()

    if args.refresh_vocab:
        return _refresh_vocab(schema, vault)

    vault.mkdir(parents=True, exist_ok=True)
    excluded = set(schema.vault.meta_doc_basenames)
    for template in sorted(TEMPLATES_DIR.glob("*.md")):
        target = vault / template.name
        if target.exists() and not args.force:
            print(f"skipped {target} (exists; use --force to overwrite)")
            continue
        target.write_text(render_template(template, schema), encoding="utf-8")
        print(f"wrote {target}")
        if not template.name.startswith("_") and template.name not in excluded:
            print(
                f"WARNING: {template.name} is not in wiki_schema.yml vault.meta_doc_basenames — "
                "it will be indexed as source content; add it and rebuild.",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
