"""Schema-driven frontmatter field extraction (Tier 2, CLAUDE.md §3/§9).

The single place that knows how to read a schema field's value out of a
frontmatter or CSV-row dict: canonical name first, then aliases; list
types coerced to lists, scalars to stripped strings; `derived` fields
skipped (the pipeline computes them); `pdf_default` applied for PDF
sidecar rows. Consumers: scripts/build/index.py (FileEntry.fields),
scripts/ingest/fetch.py (seeding), the CSV maintenance tools.
"""

from __future__ import annotations

from scripts.wiki_lib.schema import FieldSpec, WikiSchema

_LIST_TYPES = ("tag_list", "concept_list", "categorical_list")


def _as_list(v: object) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v).strip()
    return [s] if s else []


def lookup(meta: dict, spec: FieldSpec) -> object | None:
    """First non-empty value under the field's canonical name, then aliases."""
    for key in (spec.name, *spec.aliases):
        v = meta.get(key)
        if v not in (None, "", []):
            return v
    return None


def extract_fields(meta: dict, schema: WikiSchema, *, pdf: bool = False) -> dict[str, str | list[str]]:
    """One coerced value per non-derived schema field, keyed by canonical name."""
    out: dict[str, str | list[str]] = {}
    for spec in schema.frontmatter.fields:
        if spec.derived:
            continue
        raw = lookup(meta, spec)
        if spec.type in _LIST_TYPES:
            out[spec.name] = _as_list(raw)
        else:
            val = str(raw).strip() if raw is not None else ""
            if not val and pdf and spec.pdf_default is not None:
                val = spec.pdf_default
            out[spec.name] = val
    return out


def seed_missing_fields(meta: dict, schema: WikiSchema) -> None:
    """Add type-appropriate empties for schema fields absent under name AND aliases."""
    for spec in schema.frontmatter.fields:
        if spec.derived or lookup(meta, spec) is not None:
            continue
        meta[spec.name] = [] if spec.type in _LIST_TYPES else None


def enrich_meta_from_row(meta: dict, row: dict, schema: WikiSchema) -> None:
    """Fill gaps in `meta` from a CSV row, writing under the canonical name."""
    for spec in schema.frontmatter.fields:
        if spec.derived or lookup(meta, spec) is not None:
            continue
        v = lookup(row, spec)
        if v is not None:
            meta[spec.name] = v


def first_field_of_type(schema: WikiSchema, ftype: str) -> FieldSpec | None:
    return next((f for f in schema.frontmatter.fields if f.type == ftype), None)


def field_label(spec: FieldSpec) -> str:
    return spec.label or spec.name.replace("_", " ").capitalize()
