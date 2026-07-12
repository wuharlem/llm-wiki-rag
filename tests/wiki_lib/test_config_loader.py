"""Unit tests for the config loader.

Each test runs in isolation by clearing the singleton before AND after via the
autouse `reset_config_cache` fixture. Tests that need a custom config write a
temp YAML and monkeypatch `CONFIG_PATH`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

import scripts.wiki_lib.config as config_module
from scripts.wiki_lib.config import Config, _reset_config_cache, get_config


@pytest.fixture(autouse=True)
def reset_config_cache():
    """Clear the singleton before AND after each test so tests are independent."""
    _reset_config_cache()
    yield
    _reset_config_cache()


# Full valid YAML used by tests that need a temp config file. Keep keys in
# sync with the live config.yml schema.
_FULL_VALID_YAML = """\
chunking:
  target_tokens: 500
  min_tokens: 80
  max_tokens: 800
  overlap_tokens: 50
  words_per_token: 0.75

retrieval:
  bm25_k1: 1.5
  bm25_b: 0.75
  title_boost: 0.5
  heading_boost: 0.3
  rrf_k: 60
  fusion_oversample: 4
  rerank_candidates: 40
  reranker_model: "cross-encoder/ms-marco-MiniLM-L-6-v2"
  embedding_model: "BAAI/bge-small-en-v1.5"
  query_instruction: ""
  graph_expansion:
    enabled: false
    seed_hits: 5
    neighbors_per_hit: 3
    min_edge_score: 3.0

ingest:
  http_timeout_seconds: 25
  http_user_agent: "test-agent/1.0"
  skip_url_handlers:
    - github
  drop_query_param_prefixes:
    - utm_

graph:
  concept_weight: 1.0
  tag_weight: 0.5
  wikilink_weight: 3.0
  embedding_weight: 2.0
  min_cosine: 0.60
  min_edge_score: 1.0
  top_k_neighbors: 10
  louvain_seed: 42
  isolated_max_degree: 0.5
  sparse_density: 0.15
  sparse_min_size: 5
  surprising_top_n: 20
"""


def _write_full_yaml(path: Path, **chunking_overrides) -> Path:
    """Write a complete valid YAML to `path`, with optional `chunking.*` overrides."""
    data = yaml.safe_load(_FULL_VALID_YAML)
    data["chunking"].update(chunking_overrides)
    path.write_text(yaml.safe_dump(data))
    return path


def test_get_config_returns_validated_singleton():
    cfg = get_config()
    assert isinstance(cfg, Config)
    assert cfg.chunking.target_tokens == 500
    # Don't pin the tuning VALUE (it changes with legitimate config edits);
    # assert the loader read a plausible model id from the YAML.
    assert isinstance(cfg.retrieval.embedding_model, str) and "/" in cfg.retrieval.embedding_model


def test_get_config_caches_singleton(monkeypatch):
    cfg1 = get_config()
    monkeypatch.setattr(config_module, "CONFIG_PATH", Path("/nonexistent"))
    cfg2 = get_config()
    assert cfg1 is cfg2


def test_reset_config_cache_clears_singleton(monkeypatch, tmp_path):
    get_config()  # populate the cache
    custom = _write_full_yaml(tmp_path / "config.yml", target_tokens=999)
    monkeypatch.setattr(config_module, "CONFIG_PATH", custom)
    _reset_config_cache()
    cfg = get_config()
    assert cfg.chunking.target_tokens == 999


def test_unknown_yaml_key_raises_validation_error(monkeypatch, tmp_path):
    data = yaml.safe_load(_FULL_VALID_YAML)
    data["chunking"]["target_tokenz"] = 500  # typo
    bad = tmp_path / "config.yml"
    bad.write_text(yaml.safe_dump(data))
    monkeypatch.setattr(config_module, "CONFIG_PATH", bad)
    _reset_config_cache()
    with pytest.raises(ValidationError, match="target_tokenz"):
        get_config()


def test_missing_yaml_file_raises_filenotfound(monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_PATH", Path("/nonexistent/path/config.yml"))
    _reset_config_cache()
    with pytest.raises(FileNotFoundError, match="missing"):
        get_config()


def test_frozen_config_rejects_mutation():
    cfg = get_config()
    with pytest.raises(ValidationError):
        cfg.chunking.target_tokens = 600


def test_empty_yaml_raises_validation_error(monkeypatch, tmp_path):
    empty = tmp_path / "config.yml"
    empty.write_text("# empty config (only a comment)\n")
    monkeypatch.setattr(config_module, "CONFIG_PATH", empty)
    _reset_config_cache()
    with pytest.raises(ValidationError):
        get_config()


def test_malformed_yaml_raises_yaml_error(monkeypatch, tmp_path):
    bad = tmp_path / "config.yml"
    bad.write_text("chunking:\n  target_tokens: [unclosed\n")
    monkeypatch.setattr(config_module, "CONFIG_PATH", bad)
    _reset_config_cache()
    with pytest.raises(yaml.YAMLError):
        get_config()


def test_graph_config_loads(tmp_path, monkeypatch):
    p = _write_full_yaml(tmp_path / "config.yml")
    monkeypatch.setattr(config_module, "CONFIG_PATH", p)
    _reset_config_cache()
    g = get_config().graph
    assert g.wikilink_weight == 3.0
    assert g.louvain_seed == 42
    ge = get_config().retrieval.graph_expansion
    assert ge.enabled is False
    assert ge.min_edge_score == 3.0


def test_graph_config_missing_key_rejected(tmp_path, monkeypatch):
    data = yaml.safe_load(_FULL_VALID_YAML)
    del data["graph"]["louvain_seed"]
    bad = tmp_path / "config.yml"
    bad.write_text(yaml.safe_dump(data))
    monkeypatch.setattr(config_module, "CONFIG_PATH", bad)
    _reset_config_cache()
    with pytest.raises(ValidationError):
        get_config()
