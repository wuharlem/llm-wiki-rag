#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup_github.sh — one-shot: init repo, commit, create public GitHub repo,
# push.
#
# Run from the project root:
#   bash setup_github.sh
#
# Prereqs:
#   - git (always)
#   - gh CLI authenticated (`gh auth status`). If you don't have it, install
#     with `brew install gh && gh auth login`, or fall back to the manual
#     path printed at the bottom of this script.
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_NAME="ai-safety-wiki-rag"
VISIBILITY="public"
COMMIT_MSG="Initial commit: AI Safety wiki RAG + tooling

Live retrieval system over an AI Safety markdown vault, exposed as both a
CLI (scripts/query_index.py) and an MCP server (scripts/wiki_mcp_server.py).
Hybrid retrieval: BM25 + BGE-small dense embeddings + optional cross-encoder
reranker, fused via RRF.

Includes:
- Build pipeline: scripts/build_index.py, build_embeddings.py, build_wiki_index.py
- One-shot migration / cleanup scripts (most are archive candidates -- see
  CODE_AUDIT_2026-04-30.md)
- Tests: tests/ (52 tests, real-index + synthetic fixtures)
- Audit report: CODE_AUDIT_2026-04-30.md"

# Move into project root regardless of where the script was launched from.
cd "$(dirname "$0")"

echo "==> Cleaning any partial git state from the sandbox attempt..."
rm -rf .git

echo "==> Initializing fresh git repo on branch main..."
git init -b main >/dev/null

echo "==> Staging files (.gitignore is already in place)..."
git add .

echo "==> Initial commit..."
git -c user.name="Harlem Wu" -c user.email="harlemwu0930@gmail.com" \
    commit -m "$COMMIT_MSG" >/dev/null
git log --oneline -1

echo ""
echo "==> Creating $VISIBILITY GitHub repo and pushing..."
if ! command -v gh >/dev/null 2>&1; then
  echo ""
  echo "ERROR: gh CLI not found." >&2
  echo "Install with:  brew install gh && gh auth login" >&2
  echo "Or finish manually:" >&2
  echo "  1. Create the repo on https://github.com/new (name: $REPO_NAME, $VISIBILITY)" >&2
  echo "  2. git remote add origin git@github.com:<USER>/$REPO_NAME.git" >&2
  echo "  3. git push -u origin main" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo ""
  echo "ERROR: gh CLI is not authenticated. Run 'gh auth login' first." >&2
  exit 1
fi

gh repo create "$REPO_NAME" \
  --"$VISIBILITY" \
  --source=. \
  --remote=origin \
  --push \
  --description="AI Safety wiki RAG: hybrid retrieval (BM25 + dense + rerank) over a curated AI Safety markdown vault, exposed as CLI + MCP server."

echo ""
echo "==> Done."
gh repo view --json url -q .url
