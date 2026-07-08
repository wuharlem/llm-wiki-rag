"""Title cleaners salvaged from the April-2026 bulk-classification one-shot.

Source files (deleted in commit 3; see git history):
  - collapse_spaced_caps, looks_like_authors  — scripts/fix_pdf_titles.py:44, 67
  - title_from_url, slug_to_title             — scripts/fix_titles.py:83, 118
                                                (slug_to_title was _slug_to_title)
  - fix_title                                 — scripts/audit_frontmatter.py:223
  - title_from_body                           — scripts/fix_titles.py:48
  - TITLE_FIXES, TITLE_REPLACEMENTS           — scripts/audit_frontmatter.py:124, 164
                                                (inlined as module constants here so
                                                 fix_title has no back-reference to the
                                                 deleted source file)
  - is_meaningless                            — scripts/fix_titles.py:21
                                                (inlined here for title_from_body)

Lifted verbatim. The only signature change:
  - _slug_to_title → slug_to_title (drop leading underscore — it's public now).
"""

import re
from urllib.parse import unquote, urlparse

from scripts.wiki_lib.vocab import KEEP_UPPER_ACRONYMS

# Title fixes: regex pattern → replacement (apostrophe recovery, etc.)
# IMPORTANT: include leading space in pattern when replacing " S " patterns to avoid double-space artifacts.
TITLE_FIXES = [
    (re.compile(r" S Shortform\b"), "'s Shortform"),
    (re.compile(r"\bI M Optimistic\b"), "I'm Optimistic"),
    (re.compile(r"\bWhy I M\b"), "Why I'm"),
    (re.compile(r"\bYou Re\b"), "You're"),
    (re.compile(r"\bI Re\b"), "I're"),  # rare, but consistent
    (re.compile(r"\bDont\b"), "Don't"),
    (re.compile(r"\bDoesnt\b"), "Doesn't"),
    (re.compile(r"\bWont\b"), "Won't"),
    (re.compile(r"\bWasnt\b"), "Wasn't"),
    (re.compile(r"\bIsnt\b"), "Isn't"),
    (re.compile(r"\bWerent\b"), "Weren't"),
    (re.compile(r"\bArent\b"), "Aren't"),
    (re.compile(r"\bHavent\b"), "Haven't"),
    (re.compile(r"\bHasnt\b"), "Hasn't"),
    (re.compile(r"\bDidnt\b"), "Didn't"),
    (re.compile(r"\bAnthropics\b(?!\s*[A-Z])"), "Anthropic's"),
    (re.compile(r"\bOpenais\b"), "OpenAI's"),
    (re.compile(r" Openai S\b"), " OpenAI's"),
    (re.compile(r" Deepmind S\b"), " DeepMind's"),
    (re.compile(r" Apollo S\b"), " Apollo's"),
    (re.compile(r" Anthropic S\b"), " Anthropic's"),
    (re.compile(r"\bAi\b"), "AI"),  # capitalize standalone "Ai"
    # Mojibake variants
    (re.compile(r"havenât"), "haven't"),
    (re.compile(r"didnât"), "didn't"),
    (re.compile(r"isnât"), "isn't"),
    (re.compile(r"wasnât"), "wasn't"),
    (re.compile(r"wouldnât"), "wouldn't"),
    (re.compile(r"couldnât"), "couldn't"),
    (re.compile(r"shouldnât"), "shouldn't"),
    (re.compile(r"donât"), "don't"),
    (re.compile(r"itâs"), "it's"),
    (re.compile(r"thatâs"), "that's"),
    (re.compile(r"OptimizationÂ¶"), "Optimization"),
    (re.compile(r"Â¶"), ""),
    (re.compile(r"Â\b"), ""),
]

# Multi-word title fixes (string replace, applied in order)
TITLE_REPLACEMENTS = [
    ("Faq", "FAQ"),  # superintelligence faq → FAQ
    ("Sthat", "s That"),  # split run-together
    ("Anthropicâs", "Anthropic's"),
    ("Anthropicâ\x80\x99s", "Anthropic's"),
    ("â\x80\x99s", "'s"),
]


def collapse_spaced_caps(s: str) -> str:
    """Collapse 'L ANGUAGE M ODELS' → 'Language Models'.

    Pattern: a single uppercase letter followed by space and 2+ uppercase letters,
    repeated. We treat the spaced-out chars as a single small-caps word.
    """

    # Iteratively collapse pairs: 'X YYYYY' → 'Xyyyyy' where X is single cap, YYYYY is all caps
    def _collapse_word(match):
        head = match.group(1)
        tail = match.group(2)
        return head + tail.lower()

    cur = s
    # Run repeatedly until no more matches (handles back-to-back small-caps words)
    for _ in range(5):
        new = re.sub(r"\b([A-Z])\s+([A-Z]{2,})\b", _collapse_word, cur)
        if new == cur:
            break
        cur = new
    return cur


def looks_like_authors(line: str) -> bool:
    """Heuristic: line is mostly Capitalized Word pairs separated by commas/spaces."""
    # Multiple "Firstname Lastname" patterns
    if line.count(",") >= 2 and re.search(r"[A-Z][a-z]+\s+[A-Z][a-z]+", line):
        return True
    # Three+ capitalized words with no commas might also be authors
    caps = re.findall(r"[A-Z][a-z]+", line)
    if (
        len(caps) >= 4
        and len(line) < 100
        and not any(
            w.lower() in {"the", "and", "of", "for", "with", "from", "via", "into", "this", "that"}
            for w in line.split()
        )
    ):
        return True
    return False


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
        return slug_to_title(slug)
    # Alignment Forum same pattern
    if "alignmentforum.org" in p.netloc and len(parts) >= 3 and parts[0] == "posts":
        return slug_to_title(parts[2])
    # Anthropic / OpenAI / DeepMind blog: /news/<slug> or /blog/<slug> or /research/<slug>
    if parts[0] in {"news", "blog", "research", "posts", "p", "post"}:
        if len(parts) >= 2:
            return slug_to_title(parts[-1])
    # Substack: /p/<slug>
    if "substack.com" in p.netloc and len(parts) >= 2:
        return slug_to_title(parts[-1])
    # arxiv abstract: /abs/<id>
    if "arxiv.org" in p.netloc and "abs" in parts:
        return f"arXiv:{parts[-1]}"
    # Wikipedia: /wiki/<title>
    if "wikipedia.org" in p.netloc and parts[0] == "wiki":
        return slug_to_title(parts[1], strip_underscores=True) + " (Wikipedia)"
    # Default: last path segment
    return slug_to_title(parts[-1])


def slug_to_title(slug: str, strip_underscores: bool = False) -> str:
    s = slug
    # Remove trailing query / extension noise
    s = re.split(r"[?#]", s)[0]
    s = re.sub(r"\.(html|htm|pdf|md)$", "", s, flags=re.IGNORECASE)
    if strip_underscores:
        s = s.replace("_", " ")
    s = s.replace("-", " ").replace("_", " ").strip()
    if not s:
        return ""
    # Title case but preserve known acronyms
    words = s.split()
    out = []
    keep_upper = {
        "ai",
        "ml",
        "agi",
        "rlhf",
        "rlaif",
        "asl",
        "rsp",
        "llm",
        "gpu",
        "tpu",
        "api",
        "csam",
        "cbrn",
        "elk",
        "w2sg",
        "ida",
        "ppo",
        "dpo",
        "metr",
        "arc",
    }
    for w in words:
        if w.lower() in keep_upper:
            out.append(w.upper())
        else:
            out.append(w.capitalize())
    return " ".join(out)[:200]


def is_meaningless(title: str, filename: str = "") -> str:
    t = title.strip().strip("'\"")
    if not t:
        return "empty"
    if t.isdigit():
        return "numeric"
    if re.fullmatch(r"[ΩΨΣ℘\s\d\.\-]+", t):
        return "greek_numeric"
    if len(t) < 4:
        return "too_short"
    if t.lower() in {
        "ai alignment",
        "announcements",
        "untitled",
        "blog",
        "homepage",
        "search",
        "papers",
        "news",
        "research",
        "machine learning research",
        "alignment",
    }:
        return "generic"
    return ""


def title_from_body(text: str, current_url: str = "") -> str | None:
    """Extract title from trafilatura's inner metadata block or first H1 in body."""
    # Strip outer YAML frontmatter
    body = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)

    # 1. Look for trafilatura's inner metadata block: "---\ntitle: X\n..."
    inner = re.search(r"^---\s*\n(.*?)\n---\s*\n", body, re.DOTALL)
    if inner:
        inner_fm = inner.group(1)
        # Try `title: ...`
        m = re.search(r"^title:\s*(.+)$", inner_fm, re.MULTILINE)
        if m:
            cand = m.group(1).strip().strip("'\"")
            if cand and not is_meaningless(cand):
                return cand
        # Strip the inner metadata block before searching for headings
        body = body[inner.end() :]

    # 2. Look for first `# Heading` in body
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# ") and len(line) > 4:
            cand = line[2:].strip()
            cand = re.sub(r"\s+", " ", cand)[:200]
            if cand and not is_meaningless(cand):
                return cand
        if line.startswith("## ") and len(line) > 5:
            cand = line[3:].strip()
            cand = re.sub(r"\s+", " ", cand)[:200]
            if cand and not is_meaningless(cand):
                return cand

    return None


def fix_title(title: str) -> str:
    """Apply mechanical title fixes."""
    new = title
    # Apply string replacements
    for old, replacement in TITLE_REPLACEMENTS:
        new = new.replace(old, replacement)
    # Apply regex fixes
    for pat, repl in TITLE_FIXES:
        new = pat.sub(repl, new)

    # Collapse spaced-out small-caps: "L ANGUAGE" → "Language"
    def _collapse(match):
        head = match.group(1)
        tail = match.group(2)
        return head + tail.lower()

    for _ in range(5):
        prev = new
        new = re.sub(r"\b([A-Z])\s+([A-Z]{2,})\b", _collapse, new)
        if new == prev:
            break
    # Title case for known acronyms (uppercase them)
    words = new.split()
    out = []
    for w in words:
        # Strip trailing punctuation for matching
        m_punct = re.match(r"^([\w'-]+)(\W*)$", w)
        if m_punct:
            core, punct = m_punct.group(1), m_punct.group(2)
            if core.lower() in {a.lower() for a in KEEP_UPPER_ACRONYMS}:
                # Find canonical case
                for a in KEEP_UPPER_ACRONYMS:
                    if a.lower() == core.lower():
                        out.append(a + punct)
                        break
                else:
                    out.append(w)
            else:
                out.append(w)
        else:
            out.append(w)
    new = " ".join(out)
    # Normalize multiple spaces
    new = re.sub(r"\s+", " ", new).strip()
    return new
