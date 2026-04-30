"""Single source of truth for wiki_retrieval's in-memory caches.

Mutate fields via attribute assignment; reset via the invalidate() method.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RetrievalContext:
    chunks: list[dict] | None = None
    index: dict | None = None
    emb_matrix: Any = None  # numpy.ndarray when loaded
    emb_ids: list[dict] | None = None
    emb_meta: dict | None = None
    emb_chunk_index: dict[tuple[str, str], int] | None = None
    query_model: Any = None  # SentenceTransformer instance
    reranker: Any = None  # CrossEncoder instance

    def invalidate(self) -> None:
        for f in self.__dataclass_fields__:
            setattr(self, f, None)
