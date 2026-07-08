"""Single source of truth for the pipeline's tunable knobs.

Loads `config.yml` from the repo root, validates it against a frozen Pydantic
schema, and exposes the result via `get_config()`. Module-level constants in
scripts/build/index.py / scripts/serve/retrieval.py / scripts/build/embeddings.py /
scripts/ingest/fetch.py / dedup_report.py alias to fields on the returned `Config` instance.

Loud-failure contract: a missing, empty, malformed, or schema-invalid
config.yml raises at the first `get_config()` call. There is no fallback to
Python defaults — the YAML is the source of truth.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yml"

_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)


class ChunkingConfig(BaseModel):
    model_config = _MODEL_CONFIG

    target_tokens: int
    min_tokens: int
    max_tokens: int
    overlap_tokens: int
    words_per_token: float


class RetrievalConfig(BaseModel):
    model_config = _MODEL_CONFIG

    bm25_k1: float
    bm25_b: float
    title_boost: float
    heading_boost: float
    rrf_k: int
    fusion_oversample: int
    rerank_candidates: int
    reranker_model: str
    embedding_model: str


class IngestConfig(BaseModel):
    model_config = _MODEL_CONFIG

    http_timeout_seconds: int
    http_user_agent: str
    skip_url_handlers: list[str]
    drop_query_param_prefixes: list[str]


class Config(BaseModel):
    model_config = _MODEL_CONFIG

    chunking: ChunkingConfig
    retrieval: RetrievalConfig
    ingest: IngestConfig


_cached_config: Config | None = None


def get_config() -> Config:
    """Return the validated config singleton, loading config.yml on first call."""
    global _cached_config
    if _cached_config is not None:
        return _cached_config
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"missing {CONFIG_PATH}; the repo's config.yml is required")
    with CONFIG_PATH.open("r") as fh:
        data = yaml.safe_load(fh)
    _cached_config = Config.model_validate(data or {}, strict=True)
    return _cached_config


def _reset_config_cache() -> None:
    """Test hook: clear the singleton so the next get_config() re-reads the file."""
    global _cached_config
    _cached_config = None


__all__ = [
    "CONFIG_PATH",
    "Config",
    "ChunkingConfig",
    "RetrievalConfig",
    "IngestConfig",
    "get_config",
]
