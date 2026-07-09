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
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "wiki_schema.yml"

_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)


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


class FrontmatterSchema(BaseModel):
    model_config = _MODEL_CONFIG
    fields: list[FieldSpec]


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


def _reset_schema_cache() -> None:
    """Test hook: clear the singleton so the next get_schema() re-reads the file."""
    global _cached_schema
    _cached_schema = None


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
]
