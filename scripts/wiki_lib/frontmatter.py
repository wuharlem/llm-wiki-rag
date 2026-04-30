"""Canonical YAML frontmatter reader and writer for the markdown vault.

Single source of truth for parsing and emitting `---` ... `---` blocks at the
top of vault files. Lifted verbatim from `build_index.py` so the live
build pipeline and any future writer (fetch, save_query, future tools)
share identical behavior.

Public surface:
    split(text) -> (meta, body)
    dump(meta, body) -> str
    FRONTMATTER_RE, INLINE_FM_RE, KV_RE   (compiled re.Pattern constants)

Behavior notes:
- `split` parses the FIRST top-of-document `---` ... `---` block. When such a
  block is present, it ALSO strips any subsequent yamlish inline `---` blocks
  from the body (Web Clipper duplicates). When no top block is present,
  returns `({}, text)` unchanged.
- `dump` uses `yaml.safe_dump(sort_keys=False, allow_unicode=True,
  default_flow_style=False)`. Non-YAML-safe values (e.g. numpy scalars) will
  raise `yaml.representer.RepresenterError` — callers must pass plain
  Python types.
- `_tolerant_yaml` is the silent-recovery fallback used when PyYAML chokes;
  parses key:value lines via `KV_RE` and returns whatever it can recover.
"""

from __future__ import annotations

import re

import yaml

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
# Standalone --- ... --- block ANYWHERE in body, used to strip Web Clipper duplicates.
INLINE_FM_RE = re.compile(r"\n---\s*\n([^\n]*\n){1,40}?---\s*\n", re.MULTILINE)
KV_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$")


def _tolerant_yaml(block: str) -> dict:
    """Best-effort line-by-line key:value parser. Used when PyYAML chokes."""
    out: dict = {}
    for line in block.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        m = KV_RE.match(line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            out[k] = [p.strip().strip("'\"") for p in inner.split(",")] if inner else []
        elif v.lower() in ("null", "none", ""):
            out[k] = None
        else:
            out[k] = v.strip("'\"")
    return out


def split(text: str) -> tuple[dict, str]:
    """Parse the FIRST YAML frontmatter block. Return (meta, body).

    Returns `({}, text)` when no top-of-document block is present.
    When a top block is present, also strips any subsequent yamlish
    `---` ... `---` blocks from the body (Web Clipper duplicate metadata).
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    block = m.group(1)
    meta: dict = {}
    try:
        parsed = yaml.safe_load(block)
        if isinstance(parsed, dict):
            meta = parsed
    except yaml.YAMLError:
        meta = {}
    if not meta:
        meta = _tolerant_yaml(block)
    body = text[m.end() :]

    def is_yamlish(b: str) -> bool:
        lines = [ln for ln in b.strip().splitlines() if ln.strip()]
        if not lines:
            return False
        kv_hits = sum(1 for ln in lines if KV_RE.match(ln))
        return kv_hits / len(lines) >= 0.6

    while True:
        m2 = INLINE_FM_RE.search(body)
        if not m2:
            break
        block_text = m2.group(0)
        inner = block_text.strip().strip("-").strip()
        if is_yamlish(inner):
            body = body[: m2.start()] + "\n\n" + body[m2.end() :]
        else:
            break
    return meta, body


# Legacy alias used by the existing tests/test_split_frontmatter.py.
split_frontmatter = split


def dump(meta: dict, body: str) -> str:
    """Serialize (meta, body) to a markdown string with `---` frontmatter.

    Returns `f"---\\n{yaml}---\\n\\n{body}"`. Mirrors the previous inline
    construction in `fetch.py`.
    """
    yaml_text = yaml.safe_dump(
        meta, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    return f"---\n{yaml_text}---\n\n{body}"
