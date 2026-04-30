#!/usr/bin/env python3
"""
build_index.py — Build a RAG-style index over the AI Safety wiki.

Scans every .md and .pdf under VAULT, extracts text, chunks it on heading/paragraph
boundaries, generates a per-file summary (frontmatter `description` preferred),
and emits:

  01_data/index/index.json       — nested per-file metadata + summary + chunk list
  01_data/index/chunks.jsonl     — one chunk per line, for streaming retrieval
  01_data/index/manifest.csv     — flat file-level table for quick scanning
  01_data/index/build.log        — pass log
  AI Safety/_index/files/*.md    — per-file detail pages (browseable in Obsidian)

Re-runnable: caches extracted text by content hash so PDFs don't re-extract on every run.

Usage:
  python3 scripts/build_index.py                  # full build
  python3 scripts/build_index.py --md-only        # skip PDFs (faster)
  python3 scripts/build_index.py --no-detail-md   # skip per-file wiki pages
  python3 scripts/build_index.py --limit 20       # build first N for testing
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
from typing import Any

# silence pypdf's noisy crypto deprecation warning
warnings.filterwarnings("ignore", category=DeprecationWarning)

from wiki_lib.frontmatter import (
    split as split_frontmatter,
)
from wiki_lib.paths import is_indexable_path


# pypdf is only needed for PDF extraction. Defer the import so md-only
# rebuilds don't require the dependency.
def _import_pypdf():
    import pypdf  # type: ignore

    return pypdf


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
WORKDIR = SCRIPT_DIR.parent  # /AI Safety/
# Vault location may differ between the user's Mac and the sandbox mount.
# Try both.
VAULT_CANDIDATES = [
    Path("/Users/harlem/Desktop/AI Safety/AI Safety"),
]
# Fall back to any sandbox session mount (path differs each session).
# Use glob to discover live mounts; old/stale session paths can raise
# PermissionError on .exists() if the parent dir is no longer accessible.
import glob as _glob

for _p in _glob.glob("/sessions/*/mnt/AI Safety--AI Safety"):
    VAULT_CANDIDATES.append(Path(_p))


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
# Tunables
# ---------------------------------------------------------------------------
TARGET_TOKENS = 500  # rough chunk size target
MIN_TOKENS = 80  # don't emit chunks shorter than this unless final
MAX_TOKENS = 800  # hard upper bound
OVERLAP_TOKENS = 50  # carry-over between adjacent chunks
WORDS_PER_TOKEN = 0.75  # heuristic, no tokenizer dependency


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
    tags: list[str] = field(default_factory=list)
    wiki_concepts: list[str] = field(default_factory=list)
    risk_category: list[str] = field(default_factory=list)
    source_type: str = ""
    author: str = ""
    published: str = ""
    source_url: str = ""
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
    subprocess timeout in wiki_mcp_server.rebuild_index). Without this, a half-
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


def ensure_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        # comma-or-pipe separated fallback
        parts = re.split(r"[,|]", v)
        return [p.strip() for p in parts if p.strip()]
    return [str(v)]


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
    if relpath.startswith("_index/"):
        return None  # don't index ourselves
    file_id = short_id(relpath)
    raw = _scrub_text(path.read_text(errors="replace"))
    meta, body = split_frontmatter(raw)
    # if body is empty, skip
    if not body.strip():
        return None
    info = classifications.get(path.name, {})
    # Enrich missing frontmatter fields from notion_sources.csv.
    for k in (
        "title",
        "description",
        "author",
        "published",
        "source",
        "source_type",
        "tags",
        "wiki_concepts",
        "risk_category",
    ):
        csv_key = "url" if k == "source" else k
        if (not meta.get(k)) and info.get(csv_key):
            meta[k] = info[csv_key]
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
        tags=ensure_list(meta.get("tags")),
        wiki_concepts=ensure_list(meta.get("wiki_concepts")),
        risk_category=ensure_list(meta.get("risk_category")),
        source_type=str(meta.get("source_type") or "").strip(),
        author=str(meta.get("author") or "").strip(),
        published=str(meta.get("published") or "").strip(),
        source_url=str(meta.get("source") or meta.get("url") or "").strip(),
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
    summary = derive_summary("", text)
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
        tags=ensure_list(info.get("tags")),
        wiki_concepts=ensure_list(info.get("wiki_concepts")),
        risk_category=ensure_list(info.get("risk_category")),
        source_type=info.get("source_type") or "research_paper",
        author=info.get("author") or "",
        published=info.get("published") or "",
        source_url=info.get("url") or "",
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
    if entry.tags:
        lines.append("tags: [" + ", ".join(entry.tags) + "]")
    lines.append("---")
    lines.append("")
    lines.append(f"# {entry.title}")
    lines.append("")
    # link back to the source file
    rel_to_vault = entry.relpath
    obsidian_link = rel_to_vault.replace(".md", "").replace(".pdf", "")
    lines.append(f"**Source:** [[{obsidian_link}]]  ")
    if entry.source_url:
        lines.append(f"**URL:** {entry.source_url}  ")
    if entry.author:
        lines.append(f"**Author:** {entry.author}  ")
    if entry.published:
        lines.append(f"**Published:** {entry.published}  ")
    lines.append(f"**Type:** {entry.source_type or entry.type}  ")
    if entry.n_pages:
        lines.append(f"**Pages:** {entry.n_pages}  ")
    lines.append("")
    if entry.wiki_concepts:
        lines.append("**Concepts:** " + ", ".join(f"[[{c}]]" for c in entry.wiki_concepts))
    if entry.risk_category:
        lines.append("**Risk categories:** " + ", ".join(entry.risk_category))
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
    """Write chunks.jsonl atomically — one JSON object per chunk per file."""
    chunks_buf = io.StringIO()
    for e in entries:
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
                        "tags": e.tags,
                        "wiki_concepts": e.wiki_concepts,
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


def _emit_manifest_csv(entries: list[FileEntry], path: Path) -> None:
    """Write manifest.csv with the canonical 17-column header (CLAUDE.md §3)."""
    manifest_buf = io.StringIO()
    w = csv.writer(manifest_buf, quoting=csv.QUOTE_ALL, escapechar="\\", doublequote=True)
    w.writerow(
        [
            "file_id",
            "type",
            "category",
            "subcategory",
            "title",
            "n_chunks",
            "n_tokens",
            "n_pages",
            "tags",
            "wiki_concepts",
            "risk_category",
            "source_type",
            "author",
            "published",
            "source_url",
            "summary",
            "relpath",
        ]
    )

    def cell(v):
        if isinstance(v, str):
            v = v.replace("\x00", "").replace("\n", " ").replace("\r", " ")
            return v.strip()
        return v

    for e in entries:
        row = [
            e.file_id,
            e.type,
            e.category,
            e.subcategory,
            cell(e.title),
            e.n_chunks,
            e.n_tokens,
            e.n_pages,
            "|".join(str(t) for t in e.tags),
            "|".join(str(t) for t in e.wiki_concepts),
            "|".join(str(t) for t in e.risk_category),
            cell(e.source_type),
            cell(e.author),
            cell(e.published),
            cell(e.source_url),
            cell(e.summary),
            e.relpath,
        ]
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
        f.write(f"# build_index.py log — {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
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


if __name__ == "__main__":
    main()
