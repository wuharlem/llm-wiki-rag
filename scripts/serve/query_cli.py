#!/usr/bin/env python3
"""
query_cli.py — retrieval CLI over the wiki index.

Thin wrapper around scripts.serve.retrieval. Same flags and JSON output as
before — the BM25 logic was factored out into a library module so the MCP
server (scripts.serve.mcp_server) and this CLI share one code path.

    python3 -m scripts.serve.query_cli "scheming and alignment faking" --k 8

Outputs JSON to stdout. Flags:
  --k N             top N chunks (default 8)
  --category CAT    restrict to a top-level vault folder
  --concept C       restrict to files tagged with this wiki_concept
  --tag T           restrict to files with this tag
  --type {md,pdf}   restrict to MD or PDF only
  --no-text         omit chunk text in output (just metadata)
  --mode MODE       hybrid (default) | bm25 | semantic — matches the MCP server's default
"""

from __future__ import annotations

import argparse
import json
import sys

from scripts.serve.retrieval import Filters, search


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help="search query")
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--category", default=None)
    ap.add_argument("--concept", default=None)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--type", choices=["md", "pdf"], default=None, dest="file_type")
    ap.add_argument("--no-text", action="store_true")
    ap.add_argument(
        "--mode",
        choices=["bm25", "semantic", "hybrid"],
        default="hybrid",
        help="Retrieval mode (default: hybrid, matches the MCP server). "
        "Hybrid degrades gracefully to BM25 if embeddings aren't built.",
    )
    ap.add_argument(
        "--rerank", action="store_true", help="Cross-encoder re-rank the retrieval candidates (slower, more precise)."
    )
    ap.add_argument(
        "--explain",
        action="store_true",
        help="Include per-term BM25 contribution breakdown in the output (BM25 / hybrid only).",
    )
    args = ap.parse_args()

    try:
        results = search(
            args.query,
            k=args.k,
            filters=Filters(
                category=args.category,
                concept=args.concept,
                tag=args.tag,
                file_type=args.file_type,
            ),
            mode=args.mode,
            rerank_results=args.rerank,
            explain=args.explain,
        )
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if args.no_text:
        for r in results:
            r.pop("text", None)

    print(
        json.dumps(
            {
                "query": args.query,
                "mode": args.mode,
                "n_hits": len(results),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
