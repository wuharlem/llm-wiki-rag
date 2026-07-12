"""Vocabulary tables surfaced from wiki_schema.yml.

Historically these were hand-coded literals in this file. As of 2026-07-07
they are loaded lazily from wiki_schema.yml via `wiki_lib.schema.get_schema()`.
The module-level constant *names* are retained so downstream callers
(scripts.maintenance.check_vocab_sync, scripts.wiki_lib.titles) do not break.
"""

from __future__ import annotations

from scripts.wiki_lib.schema import get_schema


def _concepts() -> dict[str, list[str]]:
    return dict(get_schema().vocabulary.concepts)


def _tags() -> dict[str, list[str]]:
    return dict(get_schema().vocabulary.tags)


def _risks() -> dict[str, list[str]]:
    # Historical RISK_TRIGGERS was a flat dict; today it's one axis on the
    # schema. Guarded lookup: axis names are schema-driven and an instance
    # may rename or drop risk_category — importing this module must never
    # crash the build path. Axis-generic code should read
    # get_schema().vocabulary.categorical_axes directly.
    axis = get_schema().vocabulary.categorical_axes.get("risk_category")
    return dict(axis.values) if axis is not None else {}


def _acronyms() -> set[str]:
    return set(get_schema().vocabulary.keep_upper_acronyms)


def _acronym_map() -> dict[str, str]:
    return dict(get_schema().vocabulary.acronyms)


def _phrases() -> list[str]:
    return list(get_schema().vocabulary.phrases)


# Backwards-compatible module-level constants (evaluated at import time).
# They are snapshots — mutations will not propagate. Downstream code only reads.
WIKI_CONCEPTS: dict[str, list[str]] = _concepts()
TAG_TRIGGERS: dict[str, list[str]] = _tags()
RISK_TRIGGERS: dict[str, list[str]] = _risks()
KEEP_UPPER_ACRONYMS: set[str] = _acronyms()
ACRONYMS: dict[str, str] = _acronym_map()
PHRASES: list[str] = _phrases()
