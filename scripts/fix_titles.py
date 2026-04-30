#!/usr/bin/env python3
"""
Find files with meaningless YAML titles and rewrite them using:
  1. Trafilatura's metadata block inside the body (most reliable when present)
  2. First markdown heading in the body (skipping known junk like the trafilatura block)
  3. URL slug (turn hyphens to spaces, title-case)
  4. URL path (last segment)
"""

import csv
import re
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote
from collections import Counter

VAULT = Path(os.environ.get("VAULT", "/sessions/gifted-confident-hawking/mnt/AI Safety--AI Safety"))
WORK = Path(os.environ.get("WORK", "/sessions/gifted-confident-hawking/mnt/AI Safety"))
LOG = WORK / "02_logs" / "title_fix_log.csv"


def is_meaningless(title: str, filename: str = "") -> str:
    t = title.strip().strip("'\"")
    if not t: return "empty"
    if t.isdigit(): return "numeric"
    if re.fullmatch(r"[ΩΨΣ℘\s\d\.\-]+", t): return "greek_numeric"
    if len(t) < 4: return "too_short"
    if t.lower() in {
        "ai alignment", "announcements", "untitled", "blog", "homepage",
        "search", "papers", "news", "research", "machine learning research",
        "alignment",
    }:
        return "generic"
    return ""


def title_from_body(text: str, current_url: str = "") -> str | None:
    """Extract title from trafilatura's inner metadata block or first H1 in body."""
    # Strip outer YAML frontmatter
    body = re.sub(r'^---\n.*?\n---\n', '', text, count=1, flags=re.DOTALL)

    # 1. Look for trafilatura's inner metadata block: "---\ntitle: X\n..."
    inner = re.search(r'^---\s*\n(.*?)\n---\s*\n', body, re.DOTALL)
    if inner:
        inner_fm = inner.group(1)
        # Try `title: ...`
        m = re.search(r'^title:\s*(.+)$', inner_fm, re.MULTILINE)
        if m:
            cand = m.group(1).strip().strip("'\"")
            if cand and not is_meaningless(cand):
                return cand
        # Strip the inner metadata block before searching for headings
        body = body[inner.end():]

    # 2. Look for first `# Heading` in body
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# ") and len(line) > 4:
            cand = line[2:].strip()
            cand = re.sub(r'\s+', ' ', cand)[:200]
            if cand and not is_meaningless(cand):
                return cand
        if line.startswith("## ") and len(line) > 5:
            cand = line[3:].strip()
            cand = re.sub(r'\s+', ' ', cand)[:200]
            if cand and not is_meaningless(cand):
                return cand

    return None


def title_from_url(url: str) -> str | None:
    """Derive a title from URL slug."""
    if not url or not url.startswith("http"):
        return None
    p = urlparse(url)
    path = unquote(p.path).strip("/")
    if not path:
        # Use hostname
        return p.netloc.replace("www.", "").split(".")[0].title()
    parts = path.split("/")

    # LessWrong: /posts/<id>/<slug>
    if "lesswrong.com" in p.netloc and len(parts) >= 3 and parts[0] == "posts":
        slug = parts[2]
        return _slug_to_title(slug)
    # Alignment Forum same pattern
    if "alignmentforum.org" in p.netloc and len(parts) >= 3 and parts[0] == "posts":
        return _slug_to_title(parts[2])
    # Anthropic / OpenAI / DeepMind blog: /news/<slug> or /blog/<slug> or /research/<slug>
    if parts[0] in {"news", "blog", "research", "posts", "p", "post"}:
        if len(parts) >= 2:
            return _slug_to_title(parts[-1])
    # Substack: /p/<slug>
    if "substack.com" in p.netloc and len(parts) >= 2:
        return _slug_to_title(parts[-1])
    # arxiv abstract: /abs/<id>
    if "arxiv.org" in p.netloc and "abs" in parts:
        return f"arXiv:{parts[-1]}"
    # Wikipedia: /wiki/<title>
    if "wikipedia.org" in p.netloc and parts[0] == "wiki":
        return _slug_to_title(parts[1], strip_underscores=True) + " (Wikipedia)"
    # Default: last path segment
    return _slug_to_title(parts[-1])


def _slug_to_title(slug: str, strip_underscores: bool = False) -> str:
    s = slug
    # Remove trailing query / extension noise
    s = re.split(r'[?#]', s)[0]
    s = re.sub(r'\.(html|htm|pdf|md)$', '', s, flags=re.IGNORECASE)
    if strip_underscores:
        s = s.replace("_", " ")
    s = s.replace("-", " ").replace("_", " ").strip()
    if not s:
        return ""
    # Title case but preserve known acronyms
    words = s.split()
    out = []
    keep_upper = {"ai", "ml", "agi", "rlhf", "rlaif", "asl", "rsp", "llm", "gpu", "tpu", "api", "csam", "cbrn", "elk", "w2sg", "ida", "ppo", "dpo", "metr", "arc"}
    for w in words:
        if w.lower() in keep_upper:
            out.append(w.upper())
        else:
            out.append(w.capitalize())
    return " ".join(out)[:200]


def update_title_in_frontmatter(text: str, new_title: str) -> str:
    """Replace title: line in YAML frontmatter."""
    m = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
    if not m:
        return text
    fm = m.group(1)
    rest = text[m.end():]
    # Escape any embedded colons by quoting
    if ":" in new_title or "#" in new_title:
        title_line = f'title: "{new_title.replace(chr(34), chr(92)+chr(34))}"'
    else:
        title_line = f'title: {new_title}'
    new_fm = re.sub(r'^title:.*$', title_line, fm, count=1, flags=re.MULTILINE)
    return f'---\n{new_fm}\n---\n{rest}'


def main():
    log = []
    fixed, skipped, no_better = 0, 0, 0

    for md in VAULT.rglob("*.md"):
        if "/.obsidian/" in str(md): continue
        if "/_inbox/" in str(md): continue
        if not re.search(r'_[a-f0-9]{8}\.md$', md.name): continue

        text = md.read_text(encoding="utf-8", errors="replace")
        m = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
        if not m: continue
        fm = m.group(1)
        title_match = re.search(r'^title:\s*(.+)$', fm, re.MULTILINE)
        if not title_match: continue
        old_title = title_match.group(1).strip().strip("'\"")
        reason = is_meaningless(old_title, md.name)
        if not reason:
            continue

        url_match = re.search(r'^source:\s*(.+)$', fm, re.MULTILINE)
        url = url_match.group(1).strip() if url_match else ""

        # Try body first, then URL
        new_title = title_from_body(text, url)
        source = "body"
        if not new_title:
            new_title = title_from_url(url)
            source = "url"

        if not new_title or is_meaningless(new_title, md.name):
            no_better += 1
            log.append({
                "path": str(md.relative_to(VAULT)),
                "old": old_title, "new": "", "source": "none", "reason": reason,
            })
            continue

        new_text = update_title_in_frontmatter(text, new_title)
        md.write_text(new_text, encoding="utf-8")
        fixed += 1
        log.append({
            "path": str(md.relative_to(VAULT)),
            "old": old_title, "new": new_title, "source": source, "reason": reason,
        })

    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "old", "new", "source", "reason"])
        w.writeheader()
        w.writerows(log)

    print(f"Fixed: {fixed}")
    print(f"Could not improve: {no_better}")
    print(f"Log → {LOG}")


if __name__ == "__main__":
    main()
