#!/usr/bin/env python3
"""cli research — the open-question research-loop harness.

Owns every DETERMINISTIC step of the loop (research-loop spec 2026-07-10):
parsing open_questions.md, eligibility, three-registry URL dedup, flood
caps, and marker-safe edits. Judgment (web research, source quality,
resolve calls, briefs' content) belongs to the weekly agent driving this
command. Gated by construction: this module can stage into _add_by_me/ and
write its own markers — it must never ingest, move staged files, or write
log.md.

Subcommands: list | hits | stage | brief. Exit codes: 0 ok, 2 bad input,
3 duplicate URL, 4 cap hit.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from scripts.wiki_lib.locations import vault_path, work_path

# Flood caps (spec §2): behavioral constants of the loop, not tuning knobs —
# promote to config.yml only if they ever need per-instance tuning.
MAX_STAGED_PER_QUESTION = 4
MAX_STAGED_PER_RUN = 12
RESEARCH_STALE_DAYS = 30

_HEADING_RE = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})\] (gap|followup|methodology|thesis) \| (.+)$")
_RESEARCHED_RE = re.compile(r"^\*\*Researched:\*\* (\d{4}-\d{2}-\d{2}) — (.*) — staged \d+ source\(s\)\.$")
_STAGED_RE = re.compile(r"^  - staged: (\S+) → (\S+)$")
_RESOLVED_PREFIX = "**Resolved:**"


def _today() -> dt.date:  # test seam
    return dt.date.today()


def open_questions_path() -> Path:
    return vault_path() / "open_questions.md"


def runs_csv_path() -> Path:
    return work_path() / "02_logs" / "research_loop_runs.csv"


@dataclass
class Entry:
    date: str
    kind: str
    title: str
    slug: str
    resolved: bool
    last_researched: str | None
    brief: str | None
    staged: list[tuple[str, str]] = field(default_factory=list)
    heading_idx: int = -1
    end_idx: int = -1  # exclusive


def slugify_title(title: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", title.lower()).strip("-")
    return s[:60].rstrip("-")


def parse_entries(text: str) -> list[Entry]:
    lines = text.splitlines()
    out: list[Entry] = []
    in_fence = False
    for i, line in enumerate(lines):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(line)
        if not m:
            continue
        if out:
            out[-1].end_idx = i
        date_s, kind, title = m.groups()
        out.append(
            Entry(
                date=date_s,
                kind=kind,
                title=title.strip(),
                slug=slugify_title(title),
                resolved=_RESOLVED_PREFIX in title,
                last_researched=None,
                brief=None,
                heading_idx=i,
            )
        )
    if out:
        out[-1].end_idx = len(lines)
    for e in out:
        body = lines[e.heading_idx + 1 : e.end_idx]
        unfenced: list[str] = []
        in_fence = False
        for ln in body:
            if ln.startswith("```"):
                in_fence = not in_fence
                continue
            if not in_fence:
                unfenced.append(ln)
        first_content = next((ln for ln in unfenced if ln.strip()), "")
        if first_content.startswith(_RESOLVED_PREFIX):
            e.resolved = True
        for ln in unfenced:
            rm = _RESEARCHED_RE.match(ln)
            if rm:
                e.last_researched, e.brief = rm.group(1), rm.group(2)
            sm = _STAGED_RE.match(ln)
            if sm:
                e.staged.append((sm.group(1), sm.group(2)))
    return out


def is_eligible(e: Entry, today: dt.date) -> bool:
    if e.resolved:
        return False
    if e.last_researched is None:
        return True
    researched = dt.date.fromisoformat(e.last_researched)
    return (today - researched).days > RESEARCH_STALE_DAYS


def _load() -> tuple[list[str], list[Entry]]:
    p = open_questions_path()
    if not p.exists():
        print(f"missing {p}", file=sys.stderr)
        raise SystemExit(2)
    text = p.read_text(encoding="utf-8")
    return text.splitlines(), parse_entries(text)


def _find(entries: list[Entry], slug: str) -> Entry:
    for e in entries:
        if e.slug == slug:
            return e
    print(f"unknown slug {slug!r}; run `research list` for slugs", file=sys.stderr)
    raise SystemExit(2)


def cmd_list(args) -> int:
    _, entries = _load()
    today = _today()
    rows = [
        {
            "slug": e.slug,
            "kind": e.kind,
            "date": e.date,
            "age_days": (today - dt.date.fromisoformat(e.date)).days,
            "resolved": e.resolved,
            "last_researched": e.last_researched,
            "staged_count": len(e.staged),
            "eligible": is_eligible(e, today),
            "title": e.title,
        }
        for e in entries
    ]
    if args.eligible_only:
        rows = [r for r in rows if r["eligible"]]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        for r in rows:
            flag = "ELIGIBLE" if r["eligible"] else ("resolved" if r["resolved"] else "fresh")
            print(f"{r['slug']:60s} {r['kind']:11s} {r['date']} staged={r['staged_count']} {flag}")
    return 0


def cmd_hits(args) -> int:
    lines, entries = _load()
    e = _find(entries, args.slug)
    i, j = _entry_lines(lines, e)
    body: list[str] = []
    fence = False
    for ln in lines[i + 1 : j]:
        if ln.startswith("```"):
            fence = not fence
            continue
        if fence or not ln.strip() or _RESEARCHED_RE.match(ln) or _STAGED_RE.match(ln):
            continue
        body.append(ln)
    first_para = body[0] if body else ""
    query = f"{e.title} {first_para}".strip()[:300]

    from scripts.serve.retrieval import search  # lazy: hits is the only retrieval consumer

    results = search(query, k=args.k, mode="hybrid", rerank_results=False)
    if not results:
        print("no corpus hits")
        return 0
    for r in results:
        print(f"{r['score']:7.3f}  {r['title'][:60]:60s}  {r['relpath']}")
        print(f"         {r['text'][:200].replace(chr(10), ' ')}")
    return 0


def _marker_line(brief: str, today: dt.date, n_staged: int) -> str:
    return f"**Researched:** {today.isoformat()} — {brief} — staged {n_staged} source(s)."


def _entry_lines(lines: list[str], e: Entry) -> tuple[int, int]:
    """Re-locate the entry span by heading text (indices shift after edits)."""
    in_fence = False
    for i, ln in enumerate(lines):
        if ln.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(ln)
        if m and slugify_title(m.group(3)) == e.slug:
            j = i + 1
            fence = False
            while j < len(lines):
                if lines[j].startswith("```"):
                    fence = not fence
                elif not fence and _HEADING_RE.match(lines[j]):
                    break
                j += 1
            return i, j
    raise SystemExit(2)


def _unfenced_indices(lines: list[str], i: int, j: int) -> list[int]:
    """Line indices in [i, j) that are outside ``` fences (delimiters excluded)."""
    out: list[int] = []
    fence = False
    for k in range(i, j):
        if lines[k].startswith("```"):
            fence = not fence
            continue
        if not fence:
            out.append(k)
    return out


def _write_marker(lines: list[str], e: Entry, brief_text: str, today: dt.date) -> list[str]:
    """Create or replace the entry's Researched line; staged lines stay put."""
    i, j = _entry_lines(lines, e)
    idxs = _unfenced_indices(lines, i, j)
    n_staged = sum(1 for k in idxs if _STAGED_RE.match(lines[k]))
    new_marker = _marker_line(brief_text, today, n_staged)
    for k in idxs:
        if _RESEARCHED_RE.match(lines[k]):
            lines[k] = new_marker
            return lines
    # No marker yet: insert before trailing blank lines of the entry.
    insert_at = j
    while insert_at > i + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    return lines[:insert_at] + ["", new_marker] + lines[insert_at:]


def _append_staged_line(lines: list[str], e: Entry, url: str, fname: str) -> list[str]:
    i, j = _entry_lines(lines, e)
    idxs = _unfenced_indices(lines, i, j)
    marker_at = next((k for k in idxs if _RESEARCHED_RE.match(lines[k])), None)
    if marker_at is None:
        lines = _write_marker(lines, e, "", _today())
        i, j = _entry_lines(lines, e)
        idxs = _unfenced_indices(lines, i, j)
        marker_at = next(k for k in idxs if _RESEARCHED_RE.match(lines[k]))
    # Insert right after the marker and any directly following unfenced staged
    # lines. The marker is guaranteed unfenced, so appending immediately after
    # it is fence-safe by construction.
    at = marker_at + 1
    while at < j and _STAGED_RE.match(lines[at]):
        at += 1
    lines = lines[:at] + [f"  - staged: {url} → {fname}"] + lines[at:]
    # refresh the staged count in the marker
    i, j = _entry_lines(lines, e)
    idxs = _unfenced_indices(lines, i, j)
    n = sum(1 for k in idxs if _STAGED_RE.match(lines[k]))
    for k in idxs:
        m = _RESEARCHED_RE.match(lines[k])
        if m:
            lines[k] = _marker_line(m.group(2), dt.date.fromisoformat(m.group(1)), n)
    return lines


def _dedup_reason(url: str) -> str | None:
    """Duplicate registries: ingested (notion_sources.csv), staged (_add_by_me
    frontmatter + _PENDING.md), nominated (any entry's staged lines)."""
    from scripts.ingest.dedup_report import canonicalize_url

    cu = canonicalize_url(url)
    csv_p = work_path() / "01_data" / "notion_sources.csv"
    if csv_p.exists():
        with open(csv_p, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("url") and canonicalize_url(row["url"]) == cu:
                    return f"already ingested ({row.get('title', '?')} in notion_sources.csv)"
    staging = vault_path() / "_add_by_me"
    if staging.is_dir():
        for p in staging.glob("*.md"):
            m = re.search(r"^source_url: (\S+)$", p.read_text(encoding="utf-8", errors="replace"), re.M)
            if m and canonicalize_url(m.group(1)) == cu:
                return f"already staged ({p.name})"
        pending = staging / "_PENDING.md"
        if pending.exists() and url in pending.read_text(encoding="utf-8"):
            return "already staged (_PENDING.md)"
    _, entries = _load()
    for e in entries:
        for u, fname in e.staged:
            if canonicalize_url(u) == cu:
                return f"already nominated (under {e.slug!r} → {fname})"
    return None


def cmd_brief(args) -> int:
    lines, entries = _load()
    e = _find(entries, args.slug)
    lines = _write_marker(lines, e, " ".join(args.text.split()), _today())
    open_questions_path().write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"brief written for {e.slug}")
    return 0


def cmd_stage(args) -> int:
    lines, entries = _load()
    e = _find(entries, args.slug)
    run_id = args.run_id or _today().isoformat()

    reason = _dedup_reason(args.url)
    if reason:
        print(f"duplicate: {reason}", file=sys.stderr)
        _log_run(run_id, e.slug, args.url, f"dup: {reason}")
        return 3
    if len(e.staged) >= MAX_STAGED_PER_QUESTION:
        print(f"per-question cap ({MAX_STAGED_PER_QUESTION}) reached for {e.slug}", file=sys.stderr)
        return 4
    if _run_staged_count(run_id) >= MAX_STAGED_PER_RUN:
        print(f"per-run cap ({MAX_STAGED_PER_RUN}) reached for run {run_id}", file=sys.stderr)
        return 4

    note = f"research-loop: {e.title} ({_today().isoformat()})"
    cmd = [sys.executable, "-m", "scripts.ingest.stage_candidate", args.url, "--note", note]
    title = " ".join(args.title.split())
    if title:
        cmd += ["--title", title]
    if args.author:
        cmd += ["--author", args.author]
    if args.published:
        cmd += ["--published", args.published]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(work_path()))
    out = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"file=(\S+)", proc.stdout or "")
    if proc.returncode != 0 or not m or not (proc.stdout or "").startswith("OK"):
        print(f"stage_candidate did not succeed: {out.strip()[:300]}", file=sys.stderr)
        _log_run(run_id, e.slug, args.url, "stage_failed")
        return 2
    fname = m.group(1)

    lines = _append_staged_line(lines, e, args.url, fname)
    open_questions_path().write_text("\n".join(lines) + "\n", encoding="utf-8")
    _log_run(run_id, e.slug, args.url, "staged")
    print(f"staged {args.url} → {fname} for {e.slug}")
    return 0


def _log_run(run_id: str, slug: str, url: str, outcome: str) -> None:
    p = runs_csv_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    with open(p, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["run_id", "timestamp", "slug", "url", "outcome"])
        w.writerow([run_id, dt.datetime.now().isoformat(timespec="seconds"), slug, url, outcome])


def _run_staged_count(run_id: str) -> int:
    p = runs_csv_path()
    if not p.exists():
        return 0
    with open(p, newline="", encoding="utf-8") as fh:
        return sum(1 for row in csv.DictReader(fh) if row["run_id"] == run_id and row["outcome"] == "staged")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="research", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="live open-question entries + eligibility")
    p_list.add_argument("--json", action="store_true")
    p_list.add_argument("--eligible-only", action="store_true")
    p_list.set_defaults(fn=cmd_list)

    p_hits = sub.add_parser("hits", help="corpus retrieval for one question (resolve-check evidence)")
    p_hits.add_argument("slug")
    p_hits.add_argument("--k", type=int, default=6)
    p_hits.set_defaults(fn=cmd_hits)

    p_stage = sub.add_parser("stage", help="dedup + cap-check + stage one URL into _add_by_me/")
    p_stage.add_argument("slug")
    p_stage.add_argument("url")
    p_stage.add_argument("--title", default="")
    p_stage.add_argument("--author", default="")
    p_stage.add_argument("--published", default="")
    p_stage.add_argument("--run-id", default="")
    p_stage.set_defaults(fn=cmd_stage)

    p_brief = sub.add_parser("brief", help="write/update the entry's Researched marker")
    p_brief.add_argument("slug")
    p_brief.add_argument("--text", required=True)
    p_brief.set_defaults(fn=cmd_brief)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
