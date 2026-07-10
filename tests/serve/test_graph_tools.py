"""MCP envelopes for find_related_files / graph_insights (graph-layer spec §2)."""

from __future__ import annotations

import json

import pytest

from scripts.serve import mcp_server as ws
from scripts.serve import retrieval as wr

_FAKE_GRAPH = {
    "built_at": "2026-07-10T00:00:00+00:00",
    "n_files": 2,
    "n_edges": 1,
    "n_communities": 1,
    "params": {},
    "communities": [{"id": 0, "size": 2, "top_concepts": ["X"], "label": "X"}],
    "files": {
        "aaaaaaaaaaaa": {
            "title": "A",
            "relpath": "01/A.md",
            "community": 0,
            "degree": 5.0,
            "neighbors": [
                {
                    "file_id": "bbbbbbbbbbbb",
                    "title": "B",
                    "score": 5.0,
                    "signals": {"vocab": 2.0, "wikilink": 3.0, "embedding": 0.0},
                    "same_community": True,
                }
            ],
        },
        "bbbbbbbbbbbb": {
            "title": "B",
            "relpath": "01/B.md",
            "community": 0,
            "degree": 5.0,
            "neighbors": [
                {
                    "file_id": "aaaaaaaaaaaa",
                    "title": "A",
                    "score": 5.0,
                    "signals": {"vocab": 2.0, "wikilink": 3.0, "embedding": 0.0},
                    "same_community": True,
                }
            ],
        },
    },
    "insights": {"isolated": [], "sparse_communities": [], "bridges": [], "surprising": []},
}  # duplicated from test_graph_retrieval.py on purpose — test files are not an importable package


@pytest.fixture
def fake_graph(tmp_path, monkeypatch):
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(_FAKE_GRAPH))
    monkeypatch.setattr(wr, "GRAPH_PATH", p)
    wr.invalidate_caches()
    yield
    wr.invalidate_caches()


def test_find_related_files_tool(fake_graph):
    out = json.loads(ws.find_related_files(ws.FindRelatedFilesInput(file_id="aaaaaaaaaaaa")))
    assert out[0]["file_id"] == "bbbbbbbbbbbb"


def test_find_related_files_unknown_id(fake_graph):
    out = json.loads(ws.find_related_files(ws.FindRelatedFilesInput(file_id="ffffffffffff")))
    assert out == {"ok": False, "error": "file_not_found", "detail": out["detail"]}  # detail free-form, code stable


def test_graph_not_built(tmp_path, monkeypatch):
    monkeypatch.setattr(wr, "GRAPH_PATH", tmp_path / "nope.json")
    wr.invalidate_caches()
    out = json.loads(ws.graph_insights(ws.GraphInsightsInput()))
    assert out["ok"] is False and out["error"] == "graph_not_built"
    wr.invalidate_caches()


def test_graph_insights_kind_filter(fake_graph):
    out = json.loads(ws.graph_insights(ws.GraphInsightsInput(kind="isolated", limit=5)))
    assert list(out["insights"].keys()) == ["isolated"]
