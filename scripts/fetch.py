#!/usr/bin/env python3
"""
Bulk fetcher for AI Safety vault.

Reads urls_dedup.csv and fetches each URL into Sources/_inbox/:
  - arxiv     -> PDF (canonical pdf URL)
  - pdf       -> PDF (direct download)
  - web       -> .md (trafilatura article extraction with YAML frontmatter)
  - github/huggingface/youtube -> SKIPPED (logged)

Outputs a fetch_log.csv with status per URL.
"""

import argparse
import csv
import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
import trafilatura
from wiki_lib.config import get_config
from wiki_lib.frontmatter import dump as fm_dump
from wiki_lib.locations import vault_path, work_path

VAULT = vault_path()
WORK = work_path()
INBOX = VAULT / "Sources" / "_inbox"
DEDUP_CSV = WORK / "00_inputs" / "urls_dedup.csv"
LOG_CSV = WORK / "02_logs" / "fetch_log.csv"
SOURCES_CSV = WORK / "01_data" / "notion_sources.csv"

_CFG_INGEST = get_config().ingest
TIMEOUT = _CFG_INGEST.http_timeout_seconds
HEADERS = {"User-Agent": _CFG_INGEST.http_user_agent}
SKIP_HANDLERS = set(_CFG_INGEST.skip_url_handlers)


def slugify(s: str, maxlen: int = 120) -> str:
    s = re.sub(r"[^\w\s.\-]", "", s, flags=re.UNICODE).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:maxlen] or "untitled"


def short_hash(u: str) -> str:
    return hashlib.sha1(u.encode()).hexdigest()[:8]


def arxiv_pdf_url(u: str) -> str:
    # Normalize arxiv URLs to canonical pdf form: https://arxiv.org/pdf/<ID>.pdf
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,6})(v\d+)?", u)
    if m:
        return f"https://arxiv.org/pdf/{m.group(1)}.pdf"
    return u  # fall back to original


def arxiv_id(u: str) -> str:
    m = re.search(r"([0-9]{4}\.[0-9]{4,6})", u)
    return m.group(1) if m else short_hash(u)


def write_pdf(url: str, dest_dir: Path, name_hint: str) -> tuple[str, str]:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    ct = r.headers.get("Content-Type", "").lower()
    if "pdf" not in ct and not r.content[:5] == b"%PDF-":
        raise RuntimeError(f"not a PDF (content-type={ct})")
    fname = f"{slugify(name_hint, 80)}_{short_hash(url)}.pdf"
    path = dest_dir / fname
    path.write_bytes(r.content)
    return fname, f"{len(r.content)} bytes"


_SUSPECT_AUTHOR_PATTERNS = (
    "Authority control databases",
    "CONTRIBUTORS ",
    "MusicBrainz",
)

# Sitenames trafilatura sometimes returns AS the page title when it can't find the real one.
# When we see one of these as the title, we fall back to deriving from the URL slug.
_GENERIC_SITE_TITLES = {
    "lesswrong",
    "wikipedia",
    "reddit",
    "twitter",
    "x",
    "github",
}


def _title_from_url(url: str) -> str:
    """Best-effort title from URL path slug. e.g.
    /posts/abc123/beware-safety-washing -> Beware Safety Washing
    /p/orthogonality                     -> Orthogonality
    /tag/instrumental-convergence        -> Tag: Instrumental Convergence
    """
    try:
        path = urlparse(url).path
    except Exception:
        return ""
    parts = [p for p in path.split("/") if p]
    if not parts:
        return ""
    is_tag = "tag" in parts
    slug = parts[-1]
    # LessWrong /posts/{id}/{slug} — last segment is the readable slug
    # Strip query-fragments accidentally left in the slug
    slug = re.sub(r"\?.*$", "", slug)
    # Replace separators
    pretty = re.sub(r"[-_]+", " ", slug).strip()
    # Title-case but preserve all-caps acronyms of length <= 4
    words = []
    for w in pretty.split():
        if w.isupper() and len(w) <= 4:
            words.append(w)
        elif w.isdigit():
            words.append(w)
        else:
            words.append(w.capitalize())
    pretty = " ".join(words)
    if is_tag:
        pretty = f"Tag: {pretty}"
    return pretty


def _clean_title(raw: str, url: str) -> str:
    """If the trafilatura-returned title is a sitename, fall back to URL-slug-derived title."""
    if not raw:
        return _title_from_url(url) or ""
    t = raw.strip()
    if t.lower() in _GENERIC_SITE_TITLES:
        derived = _title_from_url(url)
        if derived:
            return derived
    return t


def _clean_date(raw: str, today: str) -> str:
    """Filter out trafilatura dates that are clearly not real publication dates.

    Returns "" (caller treats as null) if the date is suspect:
      - equals today (the page-load timestamp leaking in as 'published')
      - YYYY-01-01 (typical year-only fallback that gets coerced to Jan 1)
      - in the future (impossible)
      - before 2010 (very unlikely for an AI safety source; usually a copyright/founded year)

    Otherwise returns the cleaned ISO date. Note: at fetch time, today == created,
    so the matches-today check covers the matches-created case the cleanup script
    enforces retrospectively.
    """
    if not raw:
        return ""
    raw = raw.strip()
    # Normalize to YYYY-MM-DD if possible
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    if not m:
        return ""
    year, month, day = m.group(1), m.group(2), m.group(3)
    iso = f"{year}-{month}-{day}"
    if iso == today:
        return ""
    if month == "01" and day == "01":
        return ""
    if iso > today:
        return ""
    if int(year) < 2010:
        return ""
    return iso


def _clean_author(raw: str) -> str:
    """Filter out trafilatura author values that are clearly page metadata garbage."""
    if not raw:
        return ""
    s = raw.strip()
    for pat in _SUSPECT_AUTHOR_PATTERNS:
        if pat in s:
            return ""
    # Implausibly long author strings are usually scraped page metadata, not real bylines
    if len(s) > 200:
        return ""
    return s


def write_web_md(url: str, dest_dir: Path) -> tuple[str, str]:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    html = r.text
    extracted = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        with_metadata=True,
        include_links=True,
        include_images=False,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    if not extracted or len(extracted.strip()) < 100:
        raise RuntimeError(f"no extractable content (len={len(extracted or '')})")

    # Pull title via metadata
    meta = trafilatura.extract_metadata(html, default_url=url)
    raw_title = (meta.title if meta else None) or ""
    title = _clean_title(raw_title, url) or urlparse(url).path.strip("/").split("/")[-1] or "untitled"
    raw_author = (meta.author if meta else None) or ""
    raw_date = (meta.date if meta else None) or ""
    desc = (meta.description if meta else None) or ""

    # Build YAML frontmatter via the canonical wiki_lib.frontmatter.dump so
    # titles/descriptions
    # containing colons, quotes, or other YAML-special chars are escaped
    # correctly. Manual string concat used to corrupt the frontmatter for
    # any title like "Anthropic: a guide".
    today = datetime.now().strftime("%Y-%m-%d")
    author = _clean_author(raw_author)
    date = _clean_date(raw_date, today)
    meta: dict = {
        "title": title,
        "source": url,
        "author": author or None,
        "published": date or None,
        "created": today,
    }
    if desc:
        meta["description"] = desc
    meta["tags"] = []
    meta["concepts"] = []
    meta["risk_category"] = []
    meta["source_type"] = None
    body = f"# {title}\n\n{extracted}\n"
    out = fm_dump(meta, body)
    fname = f"{slugify(title, 100)}_{short_hash(url)}.md"
    path = dest_dir / fname
    path.write_text(out, encoding="utf-8")
    return fname, f"{len(body)} chars"


def fetch_one(row: dict) -> dict:
    url = row["url"]
    handler = row["handler"]
    out = {"url": url, "handler": handler, "status": "", "filename": "", "info": ""}
    try:
        if handler in SKIP_HANDLERS:
            out["status"] = "skipped"
            out["info"] = f"handler={handler} (skipped per policy)"
            return out
        if handler == "arxiv":
            fname, info = write_pdf(arxiv_pdf_url(url), INBOX, f"arxiv_{arxiv_id(url)}")
        elif handler == "pdf":
            fname, info = write_pdf(url, INBOX, urlparse(url).path.split("/")[-1].replace(".pdf", ""))
        elif handler == "web":
            fname, info = write_web_md(url, INBOX)
        else:
            out["status"] = "skipped"
            out["info"] = f"unknown handler={handler}"
            return out
        out["status"] = "ok"
        out["filename"] = fname
        out["info"] = info
    except Exception as e:
        out["status"] = "fail"
        out["info"] = f"{type(e).__name__}: {str(e)[:200]}"
    return out


def record_pdf_sources(results: list[dict]) -> int:
    """Append a notion_sources.csv row (filename + url) for each successfully
    fetched PDF, so build_index.py's enrichment lookup can attach the source
    URL. Markdown fetches already carry the URL in their frontmatter.
    Never overwrites existing rows. Added 2026-07-04 after the URL/tag
    backfill — without this, every new PDF regresses to url-less."""
    new = [r for r in results if r["status"] == "ok" and r["filename"].endswith(".pdf")]
    if not new or not SOURCES_CSV.exists():
        return 0
    with SOURCES_CSV.open(newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        existing = {row["filename"].strip() for row in reader}
    if "filename" not in fieldnames or "url" not in fieldnames:
        return 0
    added = 0
    with SOURCES_CSV.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        for r in new:
            if r["filename"] in existing:
                continue
            row = {k: "" for k in fieldnames}
            row["filename"] = r["filename"]
            row["url"] = r["url"]
            w.writerow(row)
            existing.add(r["filename"])
            added += 1
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only fetch first N (after handler filter)")
    ap.add_argument("--handlers", default="arxiv,pdf,web", help="comma-separated handler filter")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--sample", type=int, default=0, help="sample N from each enabled handler")
    args = ap.parse_args()

    INBOX.mkdir(parents=True, exist_ok=True)
    keep = set(args.handlers.split(","))

    rows = []
    with DEDUP_CSV.open() as f:
        for row in csv.DictReader(f):
            if row["handler"] in keep:
                rows.append(row)

    if args.sample:
        from collections import defaultdict

        grouped = defaultdict(list)
        for r in rows:
            grouped[r["handler"]].append(r)
        rows = []
        for h in keep:
            rows.extend(grouped.get(h, [])[: args.sample])

    if args.limit:
        rows = rows[: args.limit]

    print(f"Fetching {len(rows)} URLs with {args.workers} workers → {INBOX}", flush=True)
    t0 = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_one, r): r for r in rows}
        for i, fut in enumerate(as_completed(futs), 1):
            res = fut.result()
            results.append(res)
            if i % 10 == 0 or i == len(rows):
                elapsed = time.time() - t0
                ok = sum(1 for r in results if r["status"] == "ok")
                fail = sum(1 for r in results if r["status"] == "fail")
                print(f"  [{i}/{len(rows)}] ok={ok} fail={fail}  ({elapsed:.0f}s)", flush=True)

    # Write log (append-only)
    log_exists = LOG_CSV.exists()
    with LOG_CSV.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp", "url", "handler", "status", "filename", "info"])
        if not log_exists:
            w.writeheader()
        ts = datetime.now().isoformat(timespec="seconds")
        for r in results:
            r["timestamp"] = ts
            w.writerow(r)

    n_recorded = record_pdf_sources(results)

    ok = sum(1 for r in results if r["status"] == "ok")
    fail = sum(1 for r in results if r["status"] == "fail")
    skip = sum(1 for r in results if r["status"] == "skipped")
    print(f"\nDONE: {ok} ok, {fail} fail, {skip} skipped, {time.time() - t0:.0f}s total")
    print(f"Log appended → {LOG_CSV}")
    if n_recorded:
        print(f"Recorded {n_recorded} new PDF url(s) → {SOURCES_CSV}")


if __name__ == "__main__":
    main()
