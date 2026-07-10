"""Single source of truth for the vault's *domain* schema.

Loads `wiki_schema.yml` from the repo root, validates it against a frozen
Pydantic model, and exposes the result via `get_schema()`.

Distinct from `config.py`: config.py holds pipeline *tuning* knobs (chunk
sizes, BM25 params); schema.py holds *domain* declarations (which frontmatter
fields exist, what vocab they draw from, which meta docs to skip). Different
per-wiki; identical per-pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "wiki_schema.yml"

_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)

# FileEntry pipeline attributes (scripts/build/index.py) — a non-derived schema
# field with one of these names would silently shadow the pipeline's own value
# in _cell_for / the index.json flatten. Derived fields (e.g. summary) are the
# sanctioned way to expose a pipeline-computed attribute as a schema column.
_RESERVED_FIELD_NAMES = frozenset(
    {
        "file_id",
        "relpath",
        "type",
        "title",
        "folder",
        "category",
        "subcategory",
        "description",
        "summary",
        "n_pages",
        "n_chunks",
        "n_tokens",
        "body_sha1",
        "chunks",
        "fields",
    }
)

# Fixed manifest columns (scripts/build/index.py::_FIXED_LEAD/_FIXED_TAIL) —
# a schema field with one of these names would produce a DUPLICATE manifest
# column regardless of `derived`, so it is rejected outright.
# tests/meta/test_claude_md_contracts.py pins this set to index.py.
_FIXED_MANIFEST_COLUMNS = frozenset(
    {"file_id", "type", "category", "subcategory", "title", "n_chunks", "n_tokens", "n_pages", "relpath"}
)


class WikiIdentity(BaseModel):
    model_config = _MODEL_CONFIG
    name: str
    slug: str


class FieldSpec(BaseModel):
    model_config = _MODEL_CONFIG
    name: str
    type: Literal["concept_list", "categorical_list", "tag_list", "enum", "string", "date_string", "url"]
    vocab_key: str | None = None
    values: list[str] | None = None
    list_delim: str = "|"
    aliases: list[str] = []  # alternate frontmatter/CSV keys, tried after `name`
    derived: bool = False  # computed by the pipeline (e.g. summary) — never read from metadata
    label: str | None = None  # display label for detail pages; None -> derived from name
    pdf_default: str | None = None  # fallback value when a PDF sidecar row lacks the field


class FrontmatterSchema(BaseModel):
    model_config = _MODEL_CONFIG
    fields: list[FieldSpec]

    @model_validator(mode="after")
    def _no_pipeline_name_collisions(self) -> "FrontmatterSchema":
        fixed = [f.name for f in self.fields if f.name in _FIXED_MANIFEST_COLUMNS]
        if fixed:
            raise ValueError(f"frontmatter field name(s) {fixed} collide with fixed manifest columns; rename them")
        offenders = [f.name for f in self.fields if f.name in _RESERVED_FIELD_NAMES and not f.derived]
        if offenders:
            raise ValueError(
                f"frontmatter field name(s) {offenders} collide with pipeline attributes; "
                "mark them `derived: true` (pipeline-computed) or rename them"
            )
        return self


class CategoricalAxis(BaseModel):
    model_config = _MODEL_CONFIG
    values: dict[str, list[str]]


class VocabularySchema(BaseModel):
    model_config = _MODEL_CONFIG
    concepts: dict[str, list[str]]
    tags: dict[str, list[str]]
    categorical_axes: dict[str, CategoricalAxis]
    keep_upper_acronyms: list[str]


class VaultSchema(BaseModel):
    model_config = _MODEL_CONFIG
    meta_doc_basenames: list[str]
    default_relpath: list[str]
    sandbox_mount_glob: str
    # Vault-relative folder holding maintained concept articles
    # (`<slug>__synthesis.md`, one per concept). Optional so existing
    # schemas load unchanged; consumed by scripts/build/wiki_mirror.py.
    concept_articles_relpath: str = "Concepts"


class WikiSchema(BaseModel):
    model_config = _MODEL_CONFIG
    wiki: WikiIdentity
    frontmatter: FrontmatterSchema
    vocabulary: VocabularySchema
    vault: VaultSchema


_cached_schema: WikiSchema | None = None


def get_schema() -> WikiSchema:
    """Return the validated schema singleton, loading wiki_schema.yml on first call."""
    global _cached_schema
    if _cached_schema is not None:
        return _cached_schema
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"missing {SCHEMA_PATH}; the repo's wiki_schema.yml is required")
    with SCHEMA_PATH.open("r") as fh:
        data = yaml.safe_load(fh)
    _cached_schema = WikiSchema.model_validate(data or {}, strict=True)
    return _cached_schema


_cache_reset_hooks: list[Callable[[], None]] = []


def register_cache_reset_hook(hook: Callable[[], None]) -> None:
    """Register an invalidator for a schema-derived cache in another module.

    Modules that cache values computed from get_schema() (e.g. paths.py's
    meta-doc set) register a hook so _reset_schema_cache() — the test hook
    for swapping schemas — can't leave their snapshot stale (the 2026-07-09
    acceptance-test poisoning class)."""
    _cache_reset_hooks.append(hook)


def _reset_schema_cache() -> None:
    """Test hook: clear the singleton so the next get_schema() re-reads the file."""
    global _cached_schema
    _cached_schema = None
    for hook in _cache_reset_hooks:
        hook()


def mcp_server_name(schema: WikiSchema | None = None) -> str:
    """Derive the MCP server name `<slug_underscored>_wiki_mcp` (CLAUDE.md §4).

    Single derivation point shared by scripts/serve/mcp_app.py and
    scripts/maintenance/vault_init.py.
    """
    s = schema if schema is not None else get_schema()
    return f"{s.wiki.slug.replace('-', '_')}_wiki_mcp"


__all__ = [
    "SCHEMA_PATH",
    "WikiSchema",
    "WikiIdentity",
    "FieldSpec",
    "FrontmatterSchema",
    "CategoricalAxis",
    "VocabularySchema",
    "VaultSchema",
    "get_schema",
    "mcp_server_name",
    "register_cache_reset_hook",
]
