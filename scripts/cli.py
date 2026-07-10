"""scripts.cli — the stable shell surface for out-of-repo callers.

Usage:
    uv run python -m scripts.cli <command> [args...]

The command names below are a FROZEN contract (CLAUDE.md §11): vault
PROCESS docs and scheduled tasks reference only these names. Internal
modules may move freely — update COMMANDS here and nothing else changes.

Forwarding is deliberately thin: argv is rewritten and the target module
is executed via runpy under __main__, so each target keeps owning its
argparse, flags, output, and exit codes.
"""

from __future__ import annotations

import runpy
import sys

# command -> (target module, one-line description for the help table)
COMMANDS: dict[str, tuple[str, str]] = {
    "build": ("scripts.build.index", "Build the chunked RAG index (chunks.jsonl, manifest.csv)"),
    "mirror": ("scripts.build.wiki_mirror", "Rebuild the Obsidian _index/ mirror from the manifest"),
    "embed": ("scripts.build.embeddings", "Embed chunks for hybrid retrieval (run with --extra semantic)"),
    "graph": ("scripts.build.graph", "Build the file-relatedness graph (graph.json: neighbors, communities, insights)"),
    "query": ("scripts.serve.query_cli", "Query the index from the shell (BM25 + dense + RRF)"),
    "serve": ("scripts.serve.mcp_server", "Run the wiki MCP server (stdio)"),
    "fetch": ("scripts.ingest.fetch", "Bulk-fetch URLs into the vault's Sources/_inbox/"),
    "stage": ("scripts.ingest.stage_candidate", "Stage one URL into _add_by_me/ (daily-digest entrypoint)"),
    "dedup": ("scripts.ingest.dedup_report", "Report duplicate sources by canonical URL + title"),
    "cleanup": (
        "scripts.maintenance.cleanup_metadata",
        "Blank suspect published/author frontmatter (--apply to write)",
    ),
    "vocab-sync": ("scripts.maintenance.check_vocab_sync", "Lint the vault vocab table against wiki_schema.yml"),
    "notion-regen": (
        "scripts.maintenance.regenerate_notion_sources",
        "Regenerate 01_data/notion_sources.csv from vault state",
    ),
    "vault-init": (
        "scripts.maintenance.vault_init",
        "Render vault PROCESS-doc skeletons from templates/ (--refresh-vocab to resync vocab)",
    ),
}


def _print_table(stream) -> None:
    print("usage: python -m scripts.cli <command> [args...]", file=stream)
    print("commands:", file=stream)
    width = max(len(name) for name in COMMANDS)
    for name, (_target, desc) in COMMANDS.items():
        print(f"  {name:<{width}}  {desc}", file=stream)
    print("run a command with --help for its own flags", file=stream)


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] in ("-h", "--help"):
        _print_table(sys.stdout)
        raise SystemExit(0)
    command, rest = args[0], args[1:]
    entry = COMMANDS.get(command)
    if entry is None:
        print(f"unknown command: {command}", file=sys.stderr)
        _print_table(sys.stderr)
        raise SystemExit(2)
    target, _desc = entry
    sys.argv = [target, *rest]
    runpy.run_module(target, run_name="__main__")


if __name__ == "__main__":
    main()
