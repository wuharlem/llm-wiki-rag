#!/usr/bin/env python3
"""
One-shot cleaner for vault .md frontmatter — fixes the metadata-quality artifacts
the 2026-04-27 health check flagged:

  1. Suspect `published:` values from trafilatura (today, YYYY-01-01, future, < 2010)
     get blanked to `null`. The dates were bogus to begin with — better an empty
     field than a misleading one. Future ingests are filtered at the source by
     fetch.py's _clean_date helper.

  2. Suspect `author:` values that are obviously page metadata bleed
     ("Authority control databases…", "CONTRIBUTORS …", MusicBrainz junk,
     implausibly long strings) get blanked to `null`.

Dry-run is the default; pass --apply to actually write changes.
Logs every touched file to 02_logs/cleanup_metadata_log.csv.
"""

import argparse
import csv
import re
from datetime import datetime

from scripts.wiki_lib.locations import vault_path, work_path

VAULT = vault_path()
WORK = work_path()
LOG = WORK / "02_logs" / "cleanup_metadata_log.csv"

FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

_SUSPECT_AUTHOR_PATTERNS = (
    "Authority control databases",
    "CONTRIBUTORS ",
    "MusicBrainz",
)

_GENERIC_SITE_TITLES = {
    "lesswrong",
    "wikipedia",
    "reddit",
    "twitter",
    "x",
    "github",
}


def _title_from_url(url: str) -> str:
    """Best-effort title from URL path slug. Mirrors fetch.py's _title_from_url."""
    from urllib.parse import urlparse

    try:
        path = urlparse(url).path
    except Exception:
        return ""
    parts = [p for p in path.split("/") if p]
    if not parts:
        return ""
    is_tag = "tag" in parts
    slug = parts[-1]
    slug = re.sub(r"\?.*$", "", slug)
    pretty = re.sub(r"[-_]+", " ", slug).strip()
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


def clean_title(raw: str, source_url: str) -> tuple[str, str]:
    """If the title is a sitename / generic, derive from URL slug."""
    if not raw or raw.strip() in ("null", "~", ""):
        return raw, ""
    s = raw.strip().strip("\"'")
    if s.lower() in _GENERIC_SITE_TITLES:
        derived = _title_from_url(source_url)
        if derived:
            return derived, f"replaced_sitename_with_url_slug:{source_url}"
    return raw, ""


def clean_date(raw: str, today: str, created: str = "") -> tuple[str, str]:
    """Return (cleaned_date, reason_if_dropped). Empty cleaned_date == drop."""
    if not raw or raw.strip() in ("null", "~", ""):
        return raw, ""
    s = raw.strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        return s, ""  # leave non-ISO dates alone; they're rare and may carry info
    year, month, day = m.group(1), m.group(2), m.group(3)
    iso = f"{year}-{month}-{day}"
    if iso == today:
        return "null", "matches_today"
    if created and iso == created.strip():
        # Strong signal: trafilatura returned the page-load date as 'published'.
        return "null", "matches_created"
    if month == "01" and day == "01":
        return "null", "year_only_jan1_fallback"
    if iso > today:
        return "null", "future_date"
    if int(year) < 2010:
        return "null", "implausibly_old"
    return iso, ""


def clean_author(raw: str) -> tuple[str, str]:
    """Return (cleaned_author, reason_if_dropped)."""
    if not raw or raw.strip() in ("null", "~", ""):
        return raw, ""
    s = raw.strip()
    for pat in _SUSPECT_AUTHOR_PATTERNS:
        if pat in s:
            return "null", f"contains:{pat.strip()}"
    if len(s) > 200:
        return "null", f"too_long:{len(s)}"
    return s, ""


def patch_frontmatter_field(fm: str, key: str, new_value: str) -> tuple[str, bool]:
    """Replace `key: ...` line in frontmatter. Returns (new_fm, changed)."""
    pat = re.compile(rf"^{re.escape(key)}:\s*.*$", re.MULTILINE)
    m = pat.search(fm)
    if not m:
        return fm, False
    new_line = f"{key}: {new_value}"
    if m.group(0) == new_line:
        return fm, False
    return pat.sub(new_line, fm, count=1), True


def get_field(fm: str, key: str) -> str:
    pat = re.compile(rf"^{re.escape(key)}:\s*(.*)$", re.MULTILINE)
    m = pat.search(fm)
    return m.group(1).strip() if m else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write changes (default: dry-run)")
    args = ap.parse_args()

    today = datetime.now().strftime("%Y-%m-%d")
    print(f"Today (used for matches_today filter): {today}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"Vault: {VAULT}\n")

    log_rows = []
    files_touched = 0
    date_drops = 0
    author_drops = 0
    title_fixes = 0

    md_files = list(VAULT.rglob("*.md"))
    md_files = [p for p in md_files if "/.obsidian/" not in str(p) and "/_inbox/" not in str(p)]
    print(f"Scanning {len(md_files)} .md files…\n")

    for path in md_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            log_rows.append(
                {"file": str(path.relative_to(VAULT)), "field": "", "old": "", "new": "", "reason": f"read_error:{e}"}
            )
            continue

        m = FM_RE.match(text)
        if not m:
            continue
        fm = m.group(1)
        rest = text[m.end() :]

        new_fm = fm
        changed_any = False

        # Date
        old_date = get_field(new_fm, "published")
        old_created = get_field(new_fm, "created")
        new_date_val, drop_reason = clean_date(old_date, today, old_created)
        if drop_reason:
            new_fm, changed = patch_frontmatter_field(new_fm, "published", new_date_val)
            if changed:
                changed_any = True
                date_drops += 1
                log_rows.append(
                    {
                        "file": str(path.relative_to(VAULT)),
                        "field": "published",
                        "old": old_date,
                        "new": new_date_val,
                        "reason": drop_reason,
                    }
                )

        # Title (generic sitename -> URL-slug-derived)
        old_title = get_field(new_fm, "title")
        old_source = get_field(new_fm, "source")
        new_title_val, drop_reason = clean_title(old_title, old_source)
        if drop_reason:
            new_fm, changed = patch_frontmatter_field(new_fm, "title", new_title_val)
            if changed:
                changed_any = True
                title_fixes += 1
                log_rows.append(
                    {
                        "file": str(path.relative_to(VAULT)),
                        "field": "title",
                        "old": old_title,
                        "new": new_title_val,
                        "reason": drop_reason,
                    }
                )

        # Author
        old_author = get_field(new_fm, "author")
        new_author_val, drop_reason = clean_author(old_author)
        if drop_reason:
            new_fm, changed = patch_frontmatter_field(new_fm, "author", new_author_val)
            if changed:
                changed_any = True
                author_drops += 1
                log_rows.append(
                    {
                        "file": str(path.relative_to(VAULT)),
                        "field": "author",
                        "old": old_author,
                        "new": new_author_val,
                        "reason": drop_reason,
                    }
                )

        if changed_any:
            files_touched += 1
            if args.apply:
                path.write_text(f"---\n{new_fm}\n---\n{rest}", encoding="utf-8")

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "field", "old", "new", "reason"])
        w.writeheader()
        w.writerows(log_rows)

    print(f"Files scanned:       {len(md_files)}")
    print(f"Files touched:       {files_touched}")
    print(f"  date drops:        {date_drops}")
    print(f"  author drops:      {author_drops}")
    print(f"  title fixes:       {title_fixes}")
    print(f"Log → {LOG}")
    if not args.apply:
        print("\n(dry run — re-invoke with --apply to write)")


if __name__ == "__main__":
    main()
