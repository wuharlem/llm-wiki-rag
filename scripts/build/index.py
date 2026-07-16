#!/usr/bin/env python3
"""
scripts/build/index.py — Build a RAG-style index over the wiki vault.

Scans every .md and .pdf under VAULT, extracts text, chunks it on heading/paragraph
boundaries, generates a per-file summary (frontmatter `description` preferred),
and emits:

  01_data/index/index.json       — nested per-file metadata + summary + chunk list
  01_data/index/chunks.jsonl     — one chunk per line, for streaming retrieval
  01_data/index/manifest.csv     — flat file-level table for quick scanning
  01_data/index/build.log        — pass log
  <vault>/_index/files/*.md     — per-file detail pages (browseable in Obsidian)

Re-runnable: caches extracted text by content hash so PDFs don't re-extract on every run.

Usage:
  python3 -m scripts.build.index                  # full build
  python3 -m scripts.build.index --md-only        # skip PDFs (faster)
  python3 -m scripts.build.index --no-detail-md   # skip per-file wiki pages
  python3 -m scripts.build.index --limit 20       # build first N for testing
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path

# silence pypdf's noisy crypto deprecation warning
warnings.filterwarnings("ignore", category=DeprecationWarning)

from scripts.wiki_lib.config import get_config
from scripts.wiki_lib.fields import (
    enrich_meta_from_row,
    extract_fields,
    field_label,
    first_field_of_type,
)
from scripts.wiki_lib.frontmatter import (
    split as split_frontmatter,
)
from scripts.wiki_lib.locations import vault_path, work_path
from scripts.wiki_lib.paths import is_indexable_path
from scripts.wiki_lib.schema import get_schema


# pypdf is only needed for PDF extraction. Defer the import so md-only
# rebuilds don't require the dependency.
def _import_pypdf():
    import pypdf  # type: ignore

    return pypdf


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WORKDIR = work_path()
# Vault: resolved via wiki_lib.locations (env / sandbox mount / home default).
VAULT_CANDIDATES = [vault_path()]


def _safe_exists(p):
    try:
        return p.exists()
    except (PermissionError, OSError):
        return False


VAULT = next((p for p in VAULT_CANDIDATES if _safe_exists(p)), VAULT_CANDIDATES[0])

DATA_DIR = WORKDIR / "01_data" / "index"
CACHE_DIR = DATA_DIR / ".cache"
WIKI_INDEX_DIR = VAULT / "_index"
WIKI_FILES_DIR = WIKI_INDEX_DIR / "files"

# ---------------------------------------------------------------------------
# Tunables (sourced from config.yml — see scripts/wiki_lib/config.py)
# ---------------------------------------------------------------------------
_CFG_CHUNKING = get_config().chunking
TARGET_TOKENS = _CFG_CHUNKING.target_tokens
MIN_TOKENS = _CFG_CHUNKING.min_tokens
MAX_TOKENS = _CFG_CHUNKING.max_tokens
OVERLAP_TOKENS = _CFG_CHUNKING.overlap_tokens
WORDS_PER_TOKEN = _CFG_CHUNKING.words_per_token


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------
@dataclass
class Chunk:
    chunk_id: str
    heading_path: str
    text: str
    tokens: int


@dataclass
class FileEntry:
    file_id: str
    relpath: str
    type: str  # md | pdf
    title: str
    folder: str
    category: str  # top-level group, e.g. 01_Risks-and-Failure-Modes
    subcategory: str  # e.g. 01a_Existential-Risk
    description: str
    summary: str  # description if good, else derived
    fields: dict[str, str | list[str]] = field(
        default_factory=dict
    )  # schema frontmatter fields (CLAUDE.md §3), keyed by canonical name
    n_pages: int = 0  # PDFs only
    n_chunks: int = 0
    n_tokens: int = 0
    body_sha1: str = ""
    chunks: list[Chunk] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Write text to a sibling .tmp file then os.replace into place.

    Prevents torn files when a build is Ctrl-C'd or times out (e.g. the 15-min
    subprocess timeout in the MCP rebuild_index tool). Without this, a half-
    written chunks.jsonl would silently lose lines via load_all_chunks's
    JSONDecodeError handling, and a half-written embeddings_meta.json would
    leave the loader unable to start.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding=encoding)
    os.replace(tmp, path)


def short_id(s: str, n: int = 12) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


def count_tokens(text: str) -> int:
    """Rough token count: words / 0.75."""
    return max(1, int(len(text.split()) / WORDS_PER_TOKEN))


def slugify(s: str, maxlen: int = 80) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")
    return s[:maxlen] if s else "untitled"


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def split_into_blocks(body: str) -> list[tuple[str, str]]:
    """Split body into (heading_path, block_text) pairs, preserving headings."""
    # Walk lines, track current heading stack.
    blocks: list[tuple[str, str]] = []
    headings: list[str] = []  # stack indexed by depth-1
    buf: list[str] = []

    def flush():
        if buf:
            text = "\n".join(buf).strip()
            if text:
                hp = " > ".join(h for h in headings if h)
                blocks.append((hp, text))
            buf.clear()

    for line in body.splitlines():
        m = HEADING_RE.match(line)
        if m:
            flush()
            depth = len(m.group(1))
            title = m.group(2).strip()
            # resize stack
            while len(headings) < depth:
                headings.append("")
            headings = headings[:depth]
            headings[depth - 1] = title
        else:
            buf.append(line)
    flush()
    return blocks


def pack_paragraphs(text: str, target: int = TARGET_TOKENS, max_t: int = MAX_TOKENS) -> list[str]:
    """Split a long block into ~target-token sub-blocks on paragraph boundaries."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[str] = []
    cur: list[str] = []
    cur_tok = 0
    for p in paras:
        ptok = count_tokens(p)
        if ptok > max_t:
            # paragraph itself too big — split on sentences
            if cur:
                out.append("\n\n".join(cur))
                cur, cur_tok = [], 0
            sentences = re.split(r"(?<=[.!?])\s+", p)
            sbuf, stok = [], 0
            for s in sentences:
                t = count_tokens(s)
                if stok + t > max_t and sbuf:
                    out.append(" ".join(sbuf))
                    sbuf, stok = [], 0
                sbuf.append(s)
                stok += t
            if sbuf:
                out.append(" ".join(sbuf))
            continue
        if cur_tok + ptok > target and cur:
            out.append("\n\n".join(cur))
            cur, cur_tok = [], 0
        cur.append(p)
        cur_tok += ptok
    if cur:
        out.append("\n\n".join(cur))
    return out


def chunk_body(body: str) -> list[Chunk]:
    """Produce ~TARGET_TOKENS chunks with heading_path metadata."""
    blocks = split_into_blocks(body)
    chunks: list[Chunk] = []
    cur_text: list[str] = []
    cur_path = ""
    cur_tok = 0
    char_cursor = 0

    def emit(path: str, text: str):
        nonlocal char_cursor
        text = text.strip()
        if not text:
            return
        toks = count_tokens(text)
        cid = f"c{len(chunks):04d}"
        chunks.append(
            Chunk(
                chunk_id=cid,
                heading_path=path,
                text=text,
                tokens=toks,
            )
        )
        char_cursor += len(text) + 1

    for path, btext in blocks:
        btoks = count_tokens(btext)
        # If this block is huge, split it first then emit each piece under same path.
        if btoks > MAX_TOKENS:
            # flush current accumulator
            if cur_text:
                emit(cur_path, "\n\n".join(cur_text))
                cur_text, cur_tok = [], 0
            for sub in pack_paragraphs(btext):
                emit(path, sub)
            cur_path = path
            continue
        # fits on its own; try to coalesce small adjacent blocks under same heading
        if cur_text and (cur_path != path or cur_tok + btoks > TARGET_TOKENS):
            emit(cur_path, "\n\n".join(cur_text))
            cur_text, cur_tok = [], 0
        if not cur_text:
            cur_path = path
        cur_text.append(btext)
        cur_tok += btoks
        if cur_tok >= TARGET_TOKENS:
            emit(cur_path, "\n\n".join(cur_text))
            cur_text, cur_tok = [], 0

    if cur_text:
        emit(cur_path, "\n\n".join(cur_text))

    # add overlap by prepending the tail of the previous chunk to each subsequent chunk
    if OVERLAP_TOKENS and len(chunks) > 1:
        words_overlap = int(OVERLAP_TOKENS * WORDS_PER_TOKEN)
        for i in range(1, len(chunks)):
            prev_words = chunks[i - 1].text.split()
            tail = " ".join(prev_words[-words_overlap:]) if len(prev_words) > words_overlap else ""
            if tail:
                chunks[i].text = tail + " ... " + chunks[i].text
                chunks[i].tokens = count_tokens(chunks[i].text)
    return chunks


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------
def _scrub_text(s: str) -> str:
    """Drop unpaired surrogates and other invalid Unicode that breaks JSON/CSV."""
    if not s:
        return s
    # Round-trip via utf-8 with errors='replace' to drop surrogates.
    s = s.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    # collapse weird control chars except \n \t
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", s)
    return s


def extract_pdf_text(path: Path) -> tuple[str, int]:
    try:
        pypdf = _import_pypdf()
        reader = pypdf.PdfReader(str(path))
    except Exception as e:
        print(f"pdf-extract-error: {path}: {e!r}", file=sys.stderr)
        raise RuntimeError(f"pdf-extract-error: {path}: {e!r}") from e
    pages: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        txt = _scrub_text(txt)
        # mark each page so chunker can use it as a heading path
        pages.append(f"## Page {i + 1}\n\n{txt.strip()}")
    return "\n\n".join(pages), len(reader.pages)


# ---------------------------------------------------------------------------
# Summary derivation
# ---------------------------------------------------------------------------
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


def derive_summary(meta_desc: str, body: str, max_sents: int = 4) -> str:
    if meta_desc and len(meta_desc.strip()) >= 60:
        return meta_desc.strip()
    # fallback: first non-empty paragraph, capped to N sentences
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    for p in paras:
        # skip lonely headings or boilerplate
        if p.startswith("#") and len(p) < 80:
            continue
        sents = SENT_SPLIT.split(p)
        return " ".join(sents[:max_sents]).strip()
    return meta_desc.strip()


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
def cache_path(file_id: str) -> Path:
    return CACHE_DIR / f"{file_id}.txt"


def cached_extract(file_id: str, src: Path, extractor) -> tuple[str, int]:
    """extractor() returns (text, n_pages)."""
    src_hash = hashlib.sha1()
    with open(src, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            src_hash.update(chunk)
    h = src_hash.hexdigest()
    meta_p = cache_path(file_id).with_suffix(".meta.json")
    txt_p = cache_path(file_id)
    if meta_p.exists() and txt_p.exists():
        try:
            cm = json.loads(meta_p.read_text())
            if cm.get("hash") == h:
                return txt_p.read_text(), int(cm.get("n_pages", 0))
        except Exception:
            pass
    text, npages = extractor()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    txt_p.write_text(text)
    meta_p.write_text(json.dumps({"hash": h, "n_pages": npages}))
    return text, npages


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------
def process_md(path: Path, classifications: dict[str, dict]) -> FileEntry | None:
    relpath = str(path.relative_to(VAULT))
    # _index/ exclusion (except _index/saved_queries/) is handled by
    # wiki_lib.paths.is_indexable_path at file discovery — the single
    # source of truth. A blanket startswith("_index/") drop here silently
    # kept saved queries out of the index until 2026-07-04 (SQ-1).
    file_id = short_id(relpath)
    raw = _scrub_text(path.read_text(errors="replace"))
    meta, body = split_frontmatter(raw)
    # if body is empty, skip
    if not body.strip():
        return None
    info = classifications.get(path.name, {})
    # Enrich missing frontmatter from the notion_sources.csv sidecar row:
    # title/description are pipeline-fixed keys; schema fields go alias-aware.
    for k in ("title", "description"):
        if (not meta.get(k)) and info.get(k):
            meta[k] = info[k]
    enrich_meta_from_row(meta, info, get_schema())
    title = str(meta.get("title") or path.stem).strip()
    parts = relpath.split(os.sep)
    category = parts[0] if len(parts) > 1 else ""
    subcategory = parts[1] if len(parts) > 2 else ""
    folder = os.sep.join(parts[:-1])
    desc = (meta.get("description") or "").strip()
    summary = derive_summary(desc, body)
    chunks = chunk_body(body)
    return FileEntry(
        file_id=file_id,
        relpath=relpath,
        type="md",
        title=title,
        folder=folder,
        category=category,
        subcategory=subcategory,
        description=desc,
        summary=summary,
        fields=extract_fields(meta, get_schema()),
        n_pages=0,
        n_chunks=len(chunks),
        n_tokens=sum(c.tokens for c in chunks),
        body_sha1=hashlib.sha1(body.encode("utf-8")).hexdigest()[:12],
        chunks=chunks,
    )


def process_pdf(path: Path, classifications: dict[str, dict]) -> FileEntry | None:
    relpath = str(path.relative_to(VAULT))
    if relpath.startswith("_index/"):
        return None
    file_id = short_id(relpath)
    text, n_pages = cached_extract(file_id, path, lambda: extract_pdf_text(path))
    if not text.strip():
        return None
    title = path.stem.replace("_", " ")
    parts = relpath.split(os.sep)
    category = parts[0] if len(parts) > 1 else ""
    subcategory = parts[1] if len(parts) > 2 else ""
    folder = os.sep.join(parts[:-1])
    # try to enrich from classifications.csv if present
    info = classifications.get(path.name, {})
    chunks = chunk_body(text)
    # Prefer the curated csv `description` (notion_sources.csv) as the summary,
    # falling back to body extraction — mirrors the md path (process_md) so the
    # canonical per-source description drives the summary for PDFs too.
    summary = derive_summary(info.get("description") or "", text)
    return FileEntry(
        file_id=file_id,
        relpath=relpath,
        type="pdf",
        title=info.get("title") or title,
        folder=folder,
        category=category,
        subcategory=subcategory,
        description=info.get("description") or "",
        summary=summary,
        fields=extract_fields(info, get_schema(), pdf=True),
        n_pages=n_pages,
        n_chunks=len(chunks),
        n_tokens=sum(c.tokens for c in chunks),
        body_sha1=hashlib.sha1(text.encode("utf-8")).hexdigest()[:12],
        chunks=chunks,
    )


# ---------------------------------------------------------------------------
# Classifications enrichment for PDFs (and bare-frontmatter MDs)
# ---------------------------------------------------------------------------
def load_classifications() -> dict[str, dict]:
    out: dict[str, dict] = {}
    csv_p = WORKDIR / "01_data" / "notion_sources.csv"
    if not csv_p.exists():
        return out
    with open(csv_p, newline="") as f:
        for row in csv.DictReader(f):
            fn = (row.get("filename") or "").strip()
            if fn:
                out[fn] = row
    return out


# ---------------------------------------------------------------------------
# Per-file detail page (Obsidian-browseable)
# ---------------------------------------------------------------------------
def write_detail_md(entry: FileEntry) -> Path:
    WIKI_FILES_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{entry.file_id}__{slugify(entry.title)}.md"
    p = WIKI_FILES_DIR / fname
    lines: list[str] = []
    lines.append("---")
    lines.append(f'title: "{entry.title.replace(chr(34), chr(39))}"')
    lines.append(f"file_id: {entry.file_id}")
    lines.append(f"type: {entry.type}")
    lines.append(f"category: {entry.category}")
    lines.append(f"subcategory: {entry.subcategory}")
    lines.append(f"n_chunks: {entry.n_chunks}")
    lines.append(f"n_tokens: {entry.n_tokens}")
    schema = get_schema()
    tag_field = first_field_of_type(schema, "tag_list")
    tags = entry.fields.get(tag_field.name, []) if tag_field else []
    if tags:
        lines.append("tags: [" + ", ".join(tags) + "]")
    lines.append("---")
    lines.append("")
    lines.append(f"# {entry.title}")
    lines.append("")
    rel_to_vault = entry.relpath
    obsidian_link = rel_to_vault.replace(".md", "").replace(".pdf", "")
    lines.append(f"**Source:** [[{obsidian_link}]]  ")
    # Scalar schema fields as metadata rows (skip derived e.g. summary — rendered below).
    for spec in schema.frontmatter.fields:
        if spec.derived or spec.type in ("tag_list", "concept_list", "categorical_list"):
            continue
        val = entry.fields.get(spec.name, "")
        if spec.type == "enum":
            val = val or entry.type  # historic behavior: the enum row falls back to md|pdf
        if val:
            lines.append(f"**{field_label(spec)}:** {val}  ")
    if entry.n_pages:
        lines.append(f"**Pages:** {entry.n_pages}  ")
    lines.append("")
    for spec in schema.frontmatter.fields:
        vals = entry.fields.get(spec.name) or []
        if spec.type == "concept_list" and vals:
            lines.append(f"**{field_label(spec)}:** " + ", ".join(f"[[{c}]]" for c in vals))
        elif spec.type == "categorical_list" and vals:
            lines.append(f"**{field_label(spec)}:** " + ", ".join(vals))
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(entry.summary or "(no summary)")
    lines.append("")
    lines.append(f"## Chunks ({entry.n_chunks})")
    lines.append("")
    for c in entry.chunks:
        lines.append(f"### {c.chunk_id} — {c.heading_path or '(top)'} ({c.tokens} tok)")
        lines.append("")
        lines.append(c.text)
        lines.append("")
    p.write_text("\n".join(lines))
    return p


# ---------------------------------------------------------------------------
# Artifact emitters
# ---------------------------------------------------------------------------
def _emit_chunks_jsonl(entries: list[FileEntry], path: Path) -> None:
    """Write chunks.jsonl atomically — one JSON object per chunk per file.

    Chunk-record keys `tags` and `concepts` are a FROZEN retrieval contract
    (scripts/serve/retrieval.py filters on them); they are sourced from the
    first tag_list / concept_list schema field regardless of its name.
    """
    schema = get_schema()
    tag_field = first_field_of_type(schema, "tag_list")
    concept_field = first_field_of_type(schema, "concept_list")
    chunks_buf = io.StringIO()
    for e in entries:
        tags = e.fields.get(tag_field.name, []) if tag_field else []
        concepts = e.fields.get(concept_field.name, []) if concept_field else []
        for c in e.chunks:
            chunks_buf.write(
                json.dumps(
                    {
                        "file_id": e.file_id,
                        "chunk_id": c.chunk_id,
                        "relpath": e.relpath,
                        "title": e.title,
                        "category": e.category,
                        "subcategory": e.subcategory,
                        "tags": tags,
                        "concepts": concepts,
                        "heading_path": c.heading_path,
                        "tokens": c.tokens,
                        "text": c.text,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    _atomic_write_text(path, chunks_buf.getvalue())


def _emit_index_json(entries: list[FileEntry], path: Path, vault: Path) -> None:
    """Write index.json atomically — per-file metadata, no chunk text."""
    out_entries = []
    for e in entries:
        d = asdict(e)
        flds = d.pop("fields")
        ordered: dict = {}
        for k, v in d.items():
            if k == "n_pages":  # schema fields sat between summary and n_pages
                ordered.update(flds)
            ordered[k] = v
        d = ordered
        d["chunks"] = [
            {"chunk_id": c["chunk_id"], "heading_path": c["heading_path"], "tokens": c["tokens"]} for c in d["chunks"]
        ]
        out_entries.append(d)
    index_payload = {
        "vault": str(vault),
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "n_files": len(entries),
        "n_chunks": sum(e.n_chunks for e in entries),
        "n_tokens": sum(e.n_tokens for e in entries),
        "files": out_entries,
    }
    _atomic_write_text(path, json.dumps(index_payload, ensure_ascii=False, indent=2))


_FIXED_LEAD: tuple[str, ...] = (
    "file_id",
    "type",
    "category",
    "subcategory",
    "title",
    "n_chunks",
    "n_tokens",
    "n_pages",
)
_FIXED_TAIL: tuple[str, ...] = ("relpath",)


def _manifest_columns() -> tuple[str, ...]:
    """Canonical manifest columns: fixed lead + schema.frontmatter.fields + fixed tail."""
    schema_cols = tuple(f.name for f in get_schema().frontmatter.fields)
    return _FIXED_LEAD + schema_cols + _FIXED_TAIL


def _scrub_str(v: str) -> str:
    """Strip null bytes, collapse newlines/CR, trim — matches historic cell() behavior."""
    return v.replace("\x00", "").replace("\n", " ").replace("\r", " ").strip()


def _cell_for(entry: "FileEntry", col: str, list_delim: str = "|"):
    """Extract the CSV cell value for column `col` from `entry`.

    Fixed lead/tail columns are returned as-is from the FileEntry (they're ints
    or already-safe identifiers; `title` gets scrubbed like a schema string).
    Schema-driven columns dispatch on runtime type: lists are pipe-joined,
    strings are scrubbed, other scalars pass through.
    """
    if col in _FIXED_LEAD or col in _FIXED_TAIL:
        v = getattr(entry, col)
        if col == "title" and isinstance(v, str):
            return _scrub_str(v)
        return v
    val = entry.fields.get(col, getattr(entry, col, ""))
    if isinstance(val, list):
        return list_delim.join(str(t) for t in val)
    if isinstance(val, str):
        return _scrub_str(val)
    return val


def _emit_manifest_csv(entries: list[FileEntry], path: Path) -> None:
    """Write manifest.csv with columns driven by wiki_schema.yml frontmatter.fields.

    Column order: fixed build-stat lead + schema fields (in declared order) +
    `relpath`. See CLAUDE.md §3 for the cross-folder contract.
    """
    cols = _manifest_columns()
    field_delims = {f.name: f.list_delim for f in get_schema().frontmatter.fields}

    manifest_buf = io.StringIO()
    w = csv.writer(manifest_buf, quoting=csv.QUOTE_ALL, escapechar="\\", doublequote=True)
    w.writerow(list(cols))

    for e in entries:
        row = [_cell_for(e, c, list_delim=field_delims.get(c, "|")) for c in cols]
        try:
            w.writerow(row)
        except Exception as ex:
            print(f"CSV-FAIL {e.file_id} {e.relpath}: {ex}; row types: {[type(x).__name__ for x in row]}")
            w.writerow([str(x) if x is not None else "" for x in row])
    _atomic_write_text(path, manifest_buf.getvalue())


def _emit_detail_md(entries: list[FileEntry], files_dir: Path) -> None:
    """Write per-file detail pages to the wiki's _index/files/ directory."""
    files_dir.mkdir(parents=True, exist_ok=True)
    for e in entries:
        write_detail_md(e)


def _emit_build_log(entries: list[FileEntry], errors: list[tuple[str, str]], path: Path, vault: Path) -> None:
    """Write build.log — non-atomic by design; non-critical artifact."""
    with open(path, "w") as f:
        f.write(f"# scripts/build/index.py log — {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"VAULT: {vault}\n")
        f.write(f"files: {len(entries)} | chunks: {sum(e.n_chunks for e in entries)}\n")
        f.write(f"errors: {len(errors)}\n\n")
        for p, err in errors:
            f.write(f"  ERR {p}: {err}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md-only", action="store_true", help="skip PDFs")
    ap.add_argument("--no-detail-md", action="store_true", help="skip wiki per-file pages")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--vault", type=Path, default=None, help="override vault root (default: auto-discovered)")
    args = ap.parse_args()

    vault = args.vault if args.vault is not None else VAULT

    if not vault.exists():
        print(f"VAULT not found: {vault}", file=sys.stderr)
        sys.exit(1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    classifications = load_classifications()

    is_source = lambda p: is_indexable_path(p, vault)  # noqa: E731

    md_files = sorted(p for p in vault.rglob("*.md") if is_source(p))
    pdf_files = [] if args.md_only else sorted(p for p in vault.rglob("*.pdf") if is_source(p))

    if args.limit:
        md_files = md_files[: args.limit]
        pdf_files = pdf_files[: args.limit]

    targets = [(p, "md") for p in md_files] + [(p, "pdf") for p in pdf_files]
    print(f"VAULT={vault}")
    print(f"MD files: {len(md_files)} | PDF files: {len(pdf_files)} | total: {len(targets)}")

    entries: list[FileEntry] = []
    errors: list[tuple[str, str]] = []
    t0 = time.time()
    for i, (path, kind) in enumerate(targets, 1):
        try:
            if kind == "md":
                entry = process_md(path, classifications)
            else:
                entry = process_pdf(path, classifications)
        except Exception as e:
            errors.append((str(path), repr(e)))
            continue
        if entry is None:
            continue
        entries.append(entry)
        if i % 100 == 0:
            print(f"  [{i}/{len(targets)}] chunks={entry.n_chunks}")

    print(f"Extracted {len(entries)} files in {time.time() - t0:.1f}s; {len(errors)} errors")
    if errors:
        for p, e in errors[:5]:
            print(f"  err: {p}: {e}")

    chunks_p = DATA_DIR / "chunks.jsonl"
    _emit_chunks_jsonl(entries, chunks_p)
    print(f"Wrote {chunks_p}")

    index_p = DATA_DIR / "index.json"
    _emit_index_json(entries, index_p, vault)
    print(f"Wrote {index_p}")

    manifest_p = DATA_DIR / "manifest.csv"
    _emit_manifest_csv(entries, manifest_p)
    print(f"Wrote {manifest_p}")

    if not args.no_detail_md:
        _emit_detail_md(entries, WIKI_FILES_DIR)
        print(f"Wrote {len(entries)} detail pages to {WIKI_FILES_DIR}")

    log_p = DATA_DIR / "build.log"
    _emit_build_log(entries, errors, log_p, vault)
    print(f"Wrote {log_p}")
    print("Done.")

    # Debug-build guard (final-review batch 2026-07-10): --md-only and --limit
    # write a PARTIAL chunks.jsonl, and both downstream hooks treat whatever
    # is on disk as authoritative. embeddings.py's hash-delta permanently
    # DROPS every row whose (file_id, chunk_id, sha1) isn't in the current
    # chunk set — the historical md_only "drop rows" regression class (see
    # the md_only-removal note on RebuildIndexInput in
    # scripts/serve/mcp_tools/admin.py: three PDF-coverage regressions before
    # md_only was pulled from the MCP tool). graph.py has no delta of its own
    # — it recomputes the whole graph from chunks.jsonl and os.replace()s
    # graph.json every run — so a partial chunk set silently overwrites the
    # last-known-good full graph with one reflecting only the partial set.
    # Same failure class, different mechanism (drop-on-delta vs.
    # overwrite-on-full-rebuild); skip both hooks together on a debug build.
    partial_build = args.md_only or args.limit
    if not partial_build:
        # Embeddings stage (incremental-embeddings spec 2026-07-10): hash-delta,
        # so this is ~free when nothing changed. Never fails the build; catches
        # SystemExit because embeddings.main sys.exit(1)s when the semantic
        # extra isn't installed. Runs BEFORE graph (stage-order swap,
        # final-review batch 2026-07-10) so graph's embedding signal reads
        # freshly encoded vectors instead of the previous build's.
        try:
            from scripts.build import embeddings as emb_mod

            emb_mod.main([])
        except (Exception, SystemExit) as e:
            print(f"embeddings stage skipped: {e}", file=sys.stderr)

        # Graph stage (spec 2026-07-10): never fails the build.
        try:
            from scripts.build import graph as graph_mod

            graph_mod.main([])
        except Exception as e:
            print(f"graph stage skipped: {e}", file=sys.stderr)
    else:
        print(
            "embeddings/graph stages skipped: partial build (--md-only/--limit) would "
            "feed both hooks an incomplete chunks.jsonl",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
