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
import datetime as dt
import json
import re
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


def cmd_hits(args) -> int:  # implemented in Task 3
    print("hits: not implemented yet", file=sys.stderr)
    raise SystemExit(2)


def cmd_stage(args) -> int:  # implemented in Task 2
    print("stage: not implemented yet", file=sys.stderr)
    raise SystemExit(2)


def cmd_brief(args) -> int:  # implemented in Task 2
    print("brief: not implemented yet", file=sys.stderr)
    raise SystemExit(2)


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
