#!/usr/bin/env python3
"""Parse the vault's "AI Security & Safety — Researchers to Follow" markdown into
people.json + org_categories.json (written next to this script).

PROSE-FIRST UNION: the prose sections (## Category / ### Org / "- **Name**"
bullets) are the primary roster — they carry every person, their org, category,
role, description, and X/site/LinkedIn links. The "## Structured extract" table
is merged on top for structured fields (focus, papers, benchmarks, tools,
standards, talks, awards, affiliation, moved, current org, new-flag) where a
matching person exists. Table-only people (rare) are added too. This guarantees
no one is dropped just because they lack a table row.

Path-robust: locates the vault file relative to the session mount, so it runs
from any Cowork session. Reusable — lives in the persistent project folder.
"""
import re, json, os, glob, sys, unicodedata

SELF_DIR = os.path.dirname(os.path.abspath(__file__))

def find_source():
    parts = SELF_DIR.split(os.sep)
    roots = []
    if "mnt" in parts:
        roots.append(os.sep.join(parts[: parts.index("mnt") + 1]))
    roots += [os.path.expanduser("~/Desktop"), "/"]
    for root in roots:
        hits = glob.glob(os.path.join(root, "**", "AI-Security-Researchers-to-Follow.md"), recursive=True)
        hits = [h for h in hits if "/_index/" not in h and "/.claude/" not in h]
        if hits:
            return sorted(hits, key=len)[0]
    return None

SRC = find_source()
if not SRC:
    sys.exit("ERROR: could not locate AI-Security-Researchers-to-Follow.md under the session mount.")
OUT = SELF_DIR
lines = open(SRC, encoding="utf-8").read().split("\n")

def norm(n):
    n = unicodedata.normalize("NFKD", n)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.lower().replace(".", " ")
    n = re.sub(r"\b(dr|prof|professor|mr|ms|mrs)\b", " ", n)
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    return re.sub(r"\s+", " ", n).strip()

def clean(c):
    c = (c or "").strip()
    return "" if c in ("—", "-", "–", "") else c

# ---- 1. locate table start ----
tbl_start = None
for i, ln in enumerate(lines):
    if ln.startswith("## Structured extract"):
        tbl_start = i
        break
prose_end = tbl_start if tbl_start is not None else len(lines)

# ---- 2. walk prose sections (primary roster) ----
order = []                 # preserve document order
prose = {}                 # norm(name) -> record
org_cat = {}
cur_cat = cur_org = None
for ln in lines[:prose_end]:
    m = re.match(r"^##\s+(.*)", ln)
    if m and not ln.startswith("###"):
        cur_cat = m.group(1).strip(); continue
    m = re.match(r"^###\s+(.*)", ln)
    if m:
        cur_org = m.group(1).strip()
        if cur_cat: org_cat[cur_org] = cur_cat
        continue
    m = re.match(r"^-\s+\*\*(.+?)\*\*\s*(.*)$", ln)
    if not m:
        continue
    name = m.group(1).replace(" ... ", " ").replace("...", " ").strip()
    name = re.sub(r"\s+", " ", name)
    rest = m.group(2)
    # links
    x = site = linkedin = ""
    xm = re.search(r"\[@([A-Za-z0-9_]{2,})\]", rest)
    if xm: x = "https://x.com/" + xm.group(1)
    sm = re.search(r"\[🌐 site\]\((https?://[^)]+)\)", rest)
    if sm: site = sm.group(1)
    lm = re.search(r"\[in LinkedIn\]\((https?://[^)]+)\)", rest)
    if lm: linkedin = lm.group(1)
    # split "— role [handle] — blurb  ·  links"
    body = rest.lstrip("—– ").strip()
    segs = re.split(r"\s+[—–]\s+", body)
    role = re.sub(r"\s*\[[^\]]*\]\s*$", "", segs[0]).strip() if segs else ""
    blurb = ""
    if len(segs) > 1:
        blurb = " — ".join(segs[1:])
    # strip trailing link list and new-flag from blurb
    blurb = re.split(r"\s+·\s+\[", blurb)[0]
    blurb = blurb.replace("🆕", "").strip().rstrip("·").strip()
    role = role.replace("🆕", "").strip()
    key = norm(name)
    if key in prose:
        continue
    prose[key] = {
        "name": name, "org": cur_org or "", "category": cur_cat or "",
        "role": role, "blurb": blurb, "x": x, "site": site, "linkedin": linkedin,
        "isNew": "🆕" in ln,
    }
    order.append(key)

# ---- 3. parse structured table (enrichment) ----
table = {}
if tbl_start is not None:
    # Bound the table scan to THIS section only: stop at the next "## " heading.
    # (2026-07-04 fix: the scan previously ran to EOF and swallowed the
    # "## Conference & symposium participation" section added 2026-07-03,
    # turning its venue gap-list table into 19 fake people.)
    tbl_end = len(lines)
    for j in range(tbl_start + 1, len(lines)):
        if lines[j].startswith("## ") and not lines[j].startswith("###"):
            tbl_end = j
            break
    rows = []
    for ln in lines[tbl_start:tbl_end]:
        s = ln.strip()
        if not s.startswith("|"): continue
        rows.append([c.strip() for c in s.strip().strip("|").split("|")])
    data = [r for r in rows[1:] if not set("".join(r)) <= set("-: ")]
    COLS = ["Name","Organization","Focus","Papers","arXiv","Benchmarks","Tools","CVEs",
            "Standards","Talks","Awards","Affiliation","Moved","CurrentOrg","Flag"]
    for r in data:
        if len(r) < 15: r = r + [""] * (15 - len(r))
        d = dict(zip(COLS, r[:15]))
        name = re.sub(r"\s+", " ", d["Name"].replace(" ... ", " ").replace("...", " ").strip())
        if not name or name.lower() == "name": continue
        key = norm(name)
        if key in table: continue
        table[key] = {
            "name": name, "org": clean(d["Organization"]), "focus": clean(d["Focus"]),
            "notable": clean(d["Papers"]), "benchmarks": clean(d["Benchmarks"]),
            "tools": clean(d["Tools"]), "frameworks": clean(d["Standards"]),
            "talks": clean(d["Talks"]), "awards": clean(d["Awards"]),
            "affiliations": clean(d["Affiliation"]), "currentOrg": clean(d["CurrentOrg"]),
            "isNew": "🆕" in d["Flag"],
        }

# ---- 4. union: prose order first, then table-only ----
STRUCT = ["focus","notable","benchmarks","tools","frameworks","talks","awards","affiliations","currentOrg"]
people = []
seen = set()

def blank_struct():
    return {k: "" for k in STRUCT}

for key in order:
    p = dict(prose[key]); seen.add(key)
    t = table.get(key, {})
    rec = blank_struct()
    for k in STRUCT: rec[k] = t.get(k, "")
    rec.update({
        "name": p["name"], "org": p["org"] or t.get("org",""),
        "category": p["category"] or org_cat.get(t.get("org",""), "") or "Other",
        "role": p["role"], "blurb": p["blurb"],
        "x": p["x"], "site": p["site"], "linkedin": p["linkedin"],
        "isNew": p["isNew"] or t.get("isNew", False),
    })
    people.append(rec)

# table-only people (no prose bullet)
for key, t in table.items():
    if key in seen: continue
    rec = blank_struct()
    for k in STRUCT: rec[k] = t.get(k, "")
    rec.update({
        "name": t["name"], "org": t.get("org",""),
        "category": org_cat.get(t.get("org",""), "") or "Other",
        "role": "", "blurb": "", "x": "", "site": "", "linkedin": "",
        "isNew": t.get("isNew", False),
    })
    people.append(rec)

# ---- 4b. focus-tag normalization + blurb backfill (2026-07-04) ----
# Aliases merge near-duplicate focus tags into the canonical vocabulary so the
# artifact's tag chips don't show "privacy" and "privacy/DP" as separate
# filters. Backfill: people with NO focus tags (prose-only entries, no table
# row) get tags inferred by keyword-matching their role+blurb+notable text
# against the vocabulary; marked focusInferred=True so the UI could distinguish.
FOCUS_ALIASES = {
    "privacy": "privacy/DP",
    "supply chain": "supply-chain security",
    "adversarial robustness": "robustness",
    "regulation": "governance",
    "explainability": "interpretability",
    "responsible AI": "AI ethics",
    "ML security": "adversarial ML",
}
# (tag, [lowercase trigger substrings]) — order = assignment priority
TAG_KEYWORDS = [
    ("governance", ["governance", "policy", "policies", "regulat", "legislat", "treaty", "eu ai act", "diplomac"]),
    ("evaluations", ["evaluation", "evals", "dangerous capabilit", "capability assess", "audit", "safety case", "threat model"]),
    ("alignment", ["alignment", "aligning ", "reward hacking", "goal misgeneral", "deception", "deceptive", "scheming", "corrigib"]),
    ("red-teaming", ["red team", "red-team", "redteam"]),
    ("agent security", ["agent security", "agentic", "ai agents", "llm agent", "computer use"]),
    ("interpretability", ["interpretab", "mechanistic", "circuit", "probing", "activation", "sparse autoencoder", "saelens", "neuronpedia", "transparency"]),
    ("jailbreaks", ["jailbreak"]),
    ("prompt injection", ["prompt injection"]),
    ("adversarial ML", ["adversarial"]),
    ("robustness", ["robust"]),
    ("guardrails", ["guardrail", "content filter", "moderation"]),
    ("scalable oversight", ["oversight", "weak-to-strong", "debate", "ai control", "ai-control", "control protocol"]),
    ("privacy/DP", ["privacy", "differential privac", "membership inference"]),
    ("RLHF", ["rlhf", "human feedback", "reward model"]),
    ("hallucination/reliability", ["hallucinat", "factuality", "reliability"]),
    ("benchmarks", ["benchmark"]),
    ("supply-chain security", ["supply chain", "supply-chain"]),
    ("AI ethics", ["ethic", "fairness", "bias", "discriminat", "welfare", "sentience", "moral"]),
    ("multilingual safety", ["multilingual", "low-resource language"]),
    ("content safety", ["content safety", "trust and safety", "trust & safety", "child safety", "csam"]),
]
n_alias = n_backfill = 0
for p in people:
    tags, seen_t = [], set()
    for t in [x.strip() for x in (p.get("focus") or "").split(";") if x.strip()]:
        canon = FOCUS_ALIASES.get(t, t)
        if canon != t:
            n_alias += 1
        if canon.lower() not in seen_t:
            seen_t.add(canon.lower())
            tags.append(canon)
    p["focusInferred"] = False
    if not tags:
        hay = " ".join([p.get("role",""), p.get("blurb",""), p.get("notable",""), p.get("tools","")]).lower()
        for tag, kws in TAG_KEYWORDS:
            if any(k in hay for k in kws):
                tags.append(tag)
            if len(tags) >= 4:
                break
        if tags:
            p["focusInferred"] = True
            n_backfill += 1
    p["focus"] = "; ".join(tags)

# ---- 5. paper links (hybrid, one per paper): arXiv ids from blurb zipped positionally
# with notable titles; leftover titles get Scholar-search links; leftover ids get generic buttons.
import urllib.parse
ARXIV_RE = re.compile(r"arXiv[:\s]+(\d{4}\.\d{4,5})", re.I)

# Optional cache mapping arXiv id -> real title (built by the QC pass from the
# arXiv API; see arxiv_titles.json). Pairing ids with titles POSITIONALLY is
# wrong whenever the blurb cites fewer ids than the notable list has titles
# (2026-07-04 QC found 3 mislinked papers this way: Been Kim, Ahmet Üstün,
# Andy Zou). With the cache we pair by title similarity; without it we only
# pair when the mapping is unambiguous (1 id + its title first, or equal
# counts of 1) and otherwise emit Scholar links + separate arXiv buttons —
# a Scholar search is always correct, a guessed arXiv link may not be.
ARXIV_TITLES = {}
_cache = os.path.join(SELF_DIR, "arxiv_titles.json")
if os.path.exists(_cache):
    ARXIV_TITLES = json.load(open(_cache, encoding="utf-8"))

def _sim(a, b):
    aw = set(re.findall(r"[a-z0-9]+", a.lower()))
    bw = set(re.findall(r"[a-z0-9]+", b.lower()))
    return len(aw & bw) / max(1, min(len(aw), len(bw)))

for p in people:
    ids = []
    for m in ARXIV_RE.finditer(p.get("blurb", "") or ""):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    titles = [t.strip().strip("'\"“”‘’") for t in (p.get("notable") or "").split(";")]
    titles = [t for t in titles if t]

    def scholar(title):
        q = urllib.parse.quote_plus('"%s" %s' % (title, p["name"]))
        return "https://scholar.google.com/scholar?q=" + q

    papers = []
    id_for_title = {}
    used_ids = set()
    if ARXIV_TITLES and ids:
        for t in titles:
            best, best_s = None, 0.0
            for i in ids:
                if i in used_ids or i not in ARXIV_TITLES:
                    continue
                s = _sim(t, ARXIV_TITLES[i])
                if s > best_s:
                    best, best_s = i, s
            if best is not None and best_s >= 0.6:
                id_for_title[t] = best
                used_ids.add(best)
    elif len(ids) == 1 and len(titles) == 1:
        id_for_title[titles[0]] = ids[0]
        used_ids.add(ids[0])

    for t in titles:
        if t in id_for_title:
            papers.append({"u": "https://arxiv.org/abs/" + id_for_title[t], "t": t})
        else:
            papers.append({"u": scholar(t), "t": t})
    for i in ids:
        if i not in used_ids:
            papers.append({"u": "https://arxiv.org/abs/" + i, "t": "arXiv:" + i})
    p["papers"] = papers

json.dump(people, open(os.path.join(OUT, "people.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(org_cat, open(os.path.join(OUT, "org_categories.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)

linked = sum(1 for p in people if p["x"] or p["site"] or p["linkedin"])
prose_only = sum(1 for p in people if not p["focus"] and (p["blurb"] or p["role"]))
print(f"source: {SRC}")
print(f"people: {len(people)} | from prose: {len(order)} | table-only: {len(people)-len(order)}")
n_arxiv = sum(1 for p in people for pp in p["papers"] if "arxiv.org" in pp["u"])
n_scholar = sum(1 for p in people for pp in p["papers"] if "scholar.google" in pp["u"])
n_multi = sum(1 for p in people if len(p["papers"]) > 1)
print(f"with>=1 link: {linked} | new: {sum(1 for p in people if p['isNew'])} | prose-only (no table fields): {prose_only}")
still_tagless = sum(1 for p in people if not p["focus"])
print(f"focus tags: {n_alias} aliases merged | {n_backfill} people backfilled from blurb | {still_tagless} still tagless")
print(f"paper buttons: {n_arxiv} arXiv + {n_scholar} Scholar = {n_arxiv+n_scholar} across {sum(1 for p in people if p['papers'])} people ({n_multi} with 2+)")
