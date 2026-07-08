#!/usr/bin/env python3
"""Stage a single URL into the vault's `_add_by_me/` staging area.

Recurring pipeline entry point (NOT a one-shot — see CLAUDE.md §7): the
`ai-safety-daily-digest` scheduled task calls this for each ingest candidate
it surfaces, so candidates are fetched and queued instead of dying in chat.

- arXiv / direct-PDF URLs  -> PDF saved to `_add_by_me/`
- everything else (web)    -> trafilatura-extracted .md with minimal frontmatter
- every call appends a checkbox line to `_add_by_me/_PENDING.md`
  (both are index-excluded via `is_indexable_path`, so no rebuild needed)

Filenames keep the `{slug}_{8-hex-sha1-of-url}` suffix convention from
scripts.ingest.fetch (cross-folder contract §5 — do not strip).

Usage:
  python3 -m scripts.ingest.stage_candidate URL [--title T] [--note N] [--author A]
                                 [--published YYYY-MM-DD]
                                 [--content-file PATH] [--dry-run]

Two modes:
- `--content-file` (sandbox / scheduled-task mode): content was already
  fetched by the agent via the sanctioned web_fetch tool; the script only
  writes the staged .md + pending entry. No network. Preferred in Cowork.
- direct fetch (Mac mode): requests/trafilatura, works where network is
  unrestricted. In the sandbox the proxy blocks most domains (403) — the
  script then records a URL-only pending entry (FETCH_FAILED) and exits 0.
  The calling agent must NOT retry the fetch via other means.
"""

import argparse
import hashlib
import re
import sys
from datetime import date
from pathlib import Path

from scripts.wiki_lib.locations import vault_path


def find_vault() -> Path:
    # Resolver never raises on a missing vault; keep the fail-fast here.
    v = vault_path()
    if not v.is_dir():
        sys.exit("stage_candidate: vault not found (set VAULT / AI_SAFETY_VAULT)")
    return v


def slugify(s: str, maxlen: int = 120) -> str:
    s = re.sub(r"[^\w\s.\-]", "", s, flags=re.UNICODE).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:maxlen] or "untitled"


def short_hash(u: str) -> str:
    return hashlib.sha1(u.encode()).hexdigest()[:8]


def classify(url: str) -> str:
    if re.search(r"arxiv\.org/(abs|pdf)/", url):
        return "arxiv"
    if url.lower().split("?")[0].endswith(".pdf"):
        return "pdf"
    return "web"


def arxiv_pdf_url(u: str) -> str:
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,6})(v\d+)?", u)
    return f"https://arxiv.org/pdf/{m.group(1)}.pdf" if m else u


def append_pending(staging: Path, title: str, url: str, fname: str, note: str) -> None:
    pending = staging / "_PENDING.md"
    if not pending.exists():
        pending.write_text(
            "# Pending ingest candidates\n\n"
            "Appended by `scripts.ingest.stage_candidate` (daily digest task). "
            "Review, then either run PROCESS_NEW_FILE ingest on the staged file "
            "and tick the box, or delete line + file to reject.\n\n",
            encoding="utf-8",
        )
    line = f"- [ ] {date.today().isoformat()} | {title} | {url} | {fname} | {note}\n"
    with pending.open("a", encoding="utf-8") as f:
        f.write(line)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--title", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--author", default="")
    ap.add_argument("--published", default="")
    ap.add_argument("--content-file", default="", help="pre-fetched text; write as staged .md, no network")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    vault = find_vault()
    staging = vault / "_add_by_me"
    staging.mkdir(exist_ok=True)

    handler = classify(args.url)
    h = short_hash(args.url)

    # Dedupe: same URL already staged?
    if any(h in p.name for p in staging.iterdir()):
        print(f"SKIP already-staged hash={h} url={args.url}")
        return
    pending = staging / "_PENDING.md"
    if pending.exists() and args.url in pending.read_text(encoding="utf-8"):
        print(f"SKIP already-pending url={args.url}")
        return

    title = args.title or slugify(args.url.rstrip("/").split("/")[-1], 80)
    ext = ".md" if args.content_file else (".pdf" if handler in ("arxiv", "pdf") else ".md")
    fname = f"{slugify(title)}_{h}{ext}"

    def frontmatter() -> str:
        lines = ["---", f'title: "{title}"', f"source_url: {args.url}"]
        if args.author:
            lines.append(f'author: "{args.author}"')
        if args.published:
            lines.append(f"published: {args.published}")
        lines += [f"staged: {date.today().isoformat()}", f'staging_note: "{args.note}"', "---", "", ""]
        return "\n".join(lines)

    if args.dry_run:
        print(f"DRY handler={handler} file={fname}")
        return

    if args.content_file:
        body = Path(args.content_file).read_text(encoding="utf-8")
        (staging / fname).write_text(frontmatter() + body, encoding="utf-8")
        append_pending(staging, title, args.url, fname, args.note)
        print(f"OK handler=content-file file={fname}")
        return

    try:
        import requests

        headers = {"User-Agent": "Mozilla/5.0 (ai-safety-vault stage_candidate)"}
        if handler in ("arxiv", "pdf"):
            u = arxiv_pdf_url(args.url) if handler == "arxiv" else args.url
            r = requests.get(u, headers=headers, timeout=60)
            r.raise_for_status()
            (staging / fname).write_bytes(r.content)
        else:
            body = None
            try:
                import trafilatura

                downloaded = trafilatura.fetch_url(args.url)
                if downloaded:
                    body = trafilatura.extract(downloaded, include_links=False)
            except ImportError:
                pass
            if not body:
                r = requests.get(args.url, headers=headers, timeout=60)
                r.raise_for_status()
                body = r.text
            (staging / fname).write_text(frontmatter() + body, encoding="utf-8")
        append_pending(staging, title, args.url, fname, args.note)
        print(f"OK handler={handler} file={fname}")
    except Exception as e:  # record URL-only entry; caller must not retry elsewhere
        append_pending(staging, title, args.url, f"FETCH_FAILED ({type(e).__name__})", args.note)
        print(f"FAIL handler={handler} url={args.url} err={type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
