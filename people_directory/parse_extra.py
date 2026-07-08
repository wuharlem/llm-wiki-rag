#!/usr/bin/env python3
"""Build extra_data.json (papers / organizations / conferences / fellowships /
datasets) for the AI Safety Directory artifact. Companion to parse_raw.py —
run parse_raw.py first (needs people.json for cross-links).

Sources (all local, path-robust):
  papers        -> RAG manifest 01_data/index/manifest.csv (source_type research_paper|benchmark)
  organizations -> vault 05a_Educational/AI-Security-Orgs-Full-Roster-200.md (## group sections)
  conferences   -> researchers CSV `Conferences` column MERGED with notion_conferences.json
                   (snapshot of the Notion "AI Safety Conferences & Symposia" DB — re-scraped
                   manually; the connector cannot query rows live)
  fellowships   -> researchers CSV `Fellowship` column, ENRICHED with
                   notion_fellowships.json (status/deadline/funder/funding/focus
                   from the Notion "AI Safety Fellowships" DB snapshot; fuzzy
                   name match, same logic as sync_fellowships.py)
  datasets      -> researchers CSV `Benchmarks/Datasets` column + manifest benchmark rows,
                   ENRICHED with dataset_info.json (web-verified official URL /
                   one-line description / release year, 2026-07-04)
"""
import csv, json, os, re, glob, sys, datetime, unicodedata

SELF_DIR = os.path.dirname(os.path.abspath(__file__))

def find_file(pattern, extra_roots=()):
    parts = SELF_DIR.split(os.sep)
    roots = []
    if "mnt" in parts:
        roots.append(os.sep.join(parts[: parts.index("mnt") + 1]))
    roots += list(extra_roots) + [os.path.expanduser("~/Desktop"), os.path.expanduser("~/Documents")]
    for root in roots:
        hits = glob.glob(os.path.join(root, "**", pattern), recursive=True)
        hits = [h for h in hits if "/_index/" not in h and "/_trash/" not in h and "/.claude/" not in h]
        if hits:
            return sorted(hits, key=len)[0]
    return None

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def clean(v):
    v = (v or "").strip()
    return "" if v in ("—", "-", "–") else v

MANIFEST = find_file("manifest.csv")
ROSTER = find_file("AI-Security-Orgs-Full-Roster-200.md")
RES_CSV = find_file("AI-Security-Researchers-to-Follow.csv")
NOTION_CONF = os.path.join(SELF_DIR, "notion_conferences.json")
for lbl, p in [("manifest", MANIFEST), ("org roster", ROSTER), ("researchers csv", RES_CSV)]:
    if not p:
        sys.exit(f"ERROR: could not locate {lbl}")

people = json.load(open(os.path.join(SELF_DIR, "people.json"), encoding="utf-8"))
person_names = {norm(p["name"]): p["name"] for p in people}

# ---------- papers (manifest) ----------
def clean_author(a):
    a = clean(a)
    a = re.sub(r"[\[\]']", "", a.replace("[[", "").replace("]]", ""))
    a = a.strip("() ")
    return re.sub(r"\s+", " ", a)

papers = []
for r in csv.DictReader(open(MANIFEST, encoding="utf-8")):
    if r["source_type"] not in ("research_paper", "benchmark"):
        continue
    cat = re.sub(r"^\d+_", "", r["category"]).replace("-", " ")
    sub = re.sub(r"^\d+[a-z]?_", "", r["subcategory"]).replace("-", " ")
    summary = clean(r["summary"])
    if len(summary) > 300:
        summary = summary[:297].rsplit(" ", 1)[0] + "…"
    # tags = frontmatter tags UNION wiki_concepts (2026-07-04: concepts feed the
    # Papers-tab tag chips; tags alone covered only 54/448 papers)
    tags = [t for t in clean(r["tags"]).split("|") if t]
    for cpt in [t.strip() for t in clean(r.get("concepts", "")).split("|") if t.strip()]:
        if cpt not in tags:
            tags.append(cpt)
    papers.append({
        "title": clean(r["title"]), "authors": clean_author(r["author"]),
        "date": clean(r["published"]), "cat": cat, "sub": sub,
        "tags": tags[:8],
        "url": clean(r["source_url"]),
        "summary": summary,
        "kind": "benchmark" if r["source_type"] == "benchmark" else "paper",
        "pid": r.get("file_id", ""),
    })
papers.sort(key=lambda p: p["date"] or "0000", reverse=True)

# ---------- author -> people-directory matches (2026-07-04) ----------
# Scan each paper's header (the pre-"Abstract" author region of its first
# indexed chunk) for names in the people directory, and expose them as
# "rp_seed" (merged into a paper's People-directory links by gen_directory).
# Self-maintaining: recomputed each run from the freshly rebuilt RAG chunks,
# so new papers and people are picked up automatically. Full-name (2+ token)
# matches only, to avoid first-name/last-name false positives.
def _pname(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

_people_multi = {_pname(p["name"]): p["name"]
                 for p in people if len(_pname(p["name"]).split()) >= 2}
_chunks_path = os.path.join(os.path.dirname(MANIFEST), "chunks.jsonl")
_top_chunk = {}
if os.path.exists(_chunks_path):
    for _line in open(_chunks_path, encoding="utf-8"):
        try:
            _c = json.loads(_line)
        except Exception:
            continue
        if _c.get("chunk_id") == "c0000":
            _top_chunk[_c.get("file_id")] = _c.get("text", "")
n_paper_authors = 0
for pap in papers:
    txt = _top_chunk.get(pap.get("pid"))
    pap["rp_seed"] = []
    if not txt:
        continue
    _m = re.search(r"\babstract\b", txt, re.I)
    region = txt[:_m.start()] if (_m and _m.start() < 1800) else txt[:1200]
    _nr = " " + _pname(region) + " "
    hits = [_people_multi[k] for k in _people_multi if " " + k + " " in _nr]
    pap["rp_seed"] = hits
    if hits:
        n_paper_authors += 1

# ---------- organizations (roster md + people counts) ----------
org_groups, orgs = [], []
cur = None
for ln in open(ROSTER, encoding="utf-8"):
    m = re.match(r"^##\s+(.*)", ln)
    if m:
        g = m.group(1).strip()
        g = re.sub(r"\s*\(definitions:.*?\)\s*$", "", g)
        g = re.sub(r"\s*\(\d+\)\s*$", "", g).strip()
        cur = g
        org_groups.append(g)
        continue
    if cur and " · " in ln:
        for name in [x.strip() for x in ln.strip().split(" · ") if x.strip()]:
            orgs.append({"name": name, "group": cur})

# people count per org (normalized substring match both ways)
org_people = {}
for p in people:
    o = norm(p.get("org", ""))
    if o:
        org_people.setdefault(o, []).append(p["name"])
for o in orgs:
    n = norm(o["name"])
    members = list(org_people.get(n, []))
    if not members:
        for k, v in org_people.items():
            if k and (k in n or n in k) and abs(len(k) - len(n)) < 15:
                members += v
    o["people"] = sorted(set(members))

# ---------- conferences (CSV column + Notion snapshot) ----------
ROLE_RE = re.compile(r"\s*\(([^()]*(?:Speaker|Keynote|Organizer|Organiser|Delegate|Panel|Attend|Host|Judge|Mentor|Winner|Presenter|Author|Paper|Poster)[^()]*)\)\s*$", re.I)
conf_participants = {}   # norm(conf name) -> {"name": raw, "people": [{n, role}]}
res_rows = list(csv.DictReader(open(RES_CSV, encoding="utf-8")))
for r in res_rows:
    for entry in [e.strip() for e in clean(r.get("Conferences", "")).split(";") if e.strip()]:
        role = ""
        m = ROLE_RE.search(entry)
        cname = entry
        if m:
            role = m.group(1)
            cname = entry[: m.start()].strip()
        key = norm(cname)
        c = conf_participants.setdefault(key, {"name": cname, "people": []})
        c["people"].append({"n": r["Name"], "r": role})

notion = {"conferences": []}
if os.path.exists(NOTION_CONF):
    notion = json.load(open(NOTION_CONF, encoding="utf-8"))

conferences, matched = [], set()
for nc in notion["conferences"]:
    key = norm(nc.get("Name", ""))
    csv_c = conf_participants.get(key)
    if csv_c:
        matched.add(key)
    ppl = csv_c["people"] if csv_c else [{"n": x, "r": ""} for x in nc.get("Participants", [])]
    seen, uniq = set(), []
    for pp in ppl:
        if pp["n"] not in seen:
            seen.add(pp["n"]); uniq.append(pp)
    conferences.append({
        "name": nc.get("Name", ""), "year": str(nc.get("Year", "")),
        "loc": nc.get("Location", ""), "type": nc.get("Type", ""),
        "series": nc.get("Series", ""),
        "focus": nc.get("Focus area", []) if isinstance(nc.get("Focus area"), list) else [],
        "rec": nc.get("Recommendation", ""), "pri": nc.get("Join priority", ""),
        "url": nc.get("URL", ""), "notes": nc.get("Notes", ""),
        "people": uniq, "src": "notion+csv" if csv_c else "notion",
    })
YEAR_RE = re.compile(r"\b(20\d\d)\b")
# Homepage URLs for csv-only conferences (the CSV participation column has no
# URL field of its own; evidence links there are per-person, not per-venue).
# Added by the 2026-07-04 QC pass.
CSV_CONF_URLS = {
    "wef annual meeting davos 2025 2026": "https://www.weforum.org/",
    "far ai event impact of frontier ai on cyber security 2025": "https://www.far.ai/events",
    "ieee satml 2023 2024": "https://satml.org/",
    "37c3 chaos communication congress 2023": "https://events.ccc.de/congress/2023/",
}
for key, c in conf_participants.items():
    if key in matched:
        continue
    ym = YEAR_RE.search(c["name"])
    conferences.append({
        "name": c["name"], "year": ym.group(1) if ym else "", "loc": "", "type": "",
        "series": "", "focus": [], "rec": "", "pri": "", "url": CSV_CONF_URLS.get(norm(c["name"]), ""), "notes": "",
        "people": c["people"], "src": "csv",
    })
conferences.sort(key=lambda c: (c["year"] or "0000", c["name"]), reverse=True)

# ---------- fellowships (CSV Fellowship column) ----------
FELLOW_ALIASES = {"cambridge era ai": "era ai", "constellation astra": "astra", "seri mats": "mats"}
CANON_FELLOW = {}  # norm -> display
fellow_map = {}
for r in res_rows:
    raw = clean(r.get("Fellowship", ""))
    if not raw:
        continue
    for part in [x.strip() for x in re.split(r"\s*/\s*|;", raw) if x.strip()]:
        if not re.search(r"[A-Z]", part):
            continue  # junk fragment ("oversees & mentors fellows")
        base = part.split(" — ")[0]
        base = re.sub(r"\s*\([^)]*\)\s*", " ", base).strip()  # strip qualifiers for grouping
        base = re.sub(r"\s+(program advisor.*|advisory council|mentors?|alumn\w*|fellows?)\s*$", "", base, flags=re.I).strip()
        base = base or part
        key = norm(base)
        key = FELLOW_ALIASES.get(key, key)
        if not key:
            continue
        disp = CANON_FELLOW.setdefault(key, base)
        f = fellow_map.setdefault(key, {"name": disp, "people": []})
        note = part if norm(part) != key else ""
        prev = next((x for x in f["people"] if x["n"] == r["Name"]), None)
        if prev is not None:
            # dedupe: same person listed twice for one program (e.g. CSV rows
            # repeating "SPAR mentor" + "SPAR mentor (Spring 2026)") — keep
            # the more informative note
            if len(note) > len(prev["note"]):
                prev["note"] = note
            continue
        f["people"].append({"n": r["Name"], "note": note})
fellowships = sorted(fellow_map.values(), key=lambda f: -len(f["people"]))

# ---- enrich fellowships from the Notion DB snapshot (notion_fellowships.json).
# Fuzzy matching mirrors sync_fellowships.py (STOP/norm_tokens/matches).
_F_STOP = {"fellowship", "fellowships", "fellow", "fellows", "program", "programme",
           "the", "of", "for", "and", "research", "summer", "winter", "cohort",
           "institute", "in", "on", "ai", "safety", "formerly",
           # role-suffix noise from the researchers CSV ("GovAI board",
           # "Apart Research co-founder & director", "SASH advisor", ...)
           "advisor", "affiliate", "board", "mentor", "mentors", "alumni",
           "alumnus", "co", "founder", "cofounder", "director", "supervisor",
           "speaker", "organizer", "former", "senior", "strategy"}

def _f_tokens(name):
    n = re.sub(r"[()\[\]]", " ", name.lower())
    n = re.sub(r"[—–\-/×:]", " ", n)
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    return {t for t in n.split() if t and t not in _F_STOP and not t.isdigit()}

def _f_matches(a_name, b_name):
    a, b = _f_tokens(a_name), _f_tokens(b_name)
    if not a or not b:
        return False
    return a <= b or b <= a or (len(a & b) >= 2)

NOTION_FELLOW = os.path.join(SELF_DIR, "notion_fellowships.json")
n_fellow_enriched = 0
if os.path.exists(NOTION_FELLOW):
    fsnap = json.load(open(NOTION_FELLOW, encoding="utf-8"))
    for f in fellowships:
        row = next((r for r in fsnap.get("rows", []) if _f_matches(f["name"], r["program"])), None)
        if row:
            f["status"] = clean(row.get("status", ""))
            f["deadline"] = clean(row.get("deadline", ""))
            f["funder"] = clean(row.get("funder", ""))
            f["funding"] = clean(row.get("funding", ""))
            f["focus"] = clean(row.get("focus", ""))
            f["focus_areas"] = row.get("focus_areas", []) or []
            f["link"] = clean(row.get("link", ""))
            f["program_full"] = row.get("program", "")
            n_fellow_enriched += 1

# ---- merge role-variant cards (2026-07-04): the CSV yields near-dupes like
# "GovAI" / "GovAI board" / "GovAI affiliate" as separate programs. Variants
# resolve to the same Notion row, so group by matched program (norm(name) for
# the unmatched); display name = shortest variant; the variant label is kept
# as the person's note so role info isn't lost.
_pre_merge = len(fellowships)
_fmerged, _forder = {}, []
for f in fellowships:
    gkey = norm(f.get("program_full") or f["name"])
    g = _fmerged.get(gkey)
    if g is None:
        _fmerged[gkey] = f
        _forder.append(gkey)
        continue
    vname = f["name"]
    if len(vname) < len(g["name"]):
        # group leader was itself a role-variant ("Talos board" before
        # "Talos" arrived): retro-label its people before renaming
        old = g["name"]
        if norm(old) != norm(vname):
            for x in g["people"]:
                if not x["note"]:
                    x["note"] = old
        g["name"] = vname
    for pe in f["people"]:
        note = pe["note"] or (vname if norm(vname) != norm(g["name"]) else "")
        prev = next((x for x in g["people"] if x["n"] == pe["n"]), None)
        if prev is None:
            g["people"].append({"n": pe["n"], "note": note})
        elif len(note) > len(prev["note"]):
            prev["note"] = note
fellowships = sorted((_fmerged[k] for k in _forder), key=lambda f: -len(f["people"]))
n_fellow_merged = _pre_merge - len(fellowships)

# ---------- datasets (CSV column + manifest benchmark URLs) ----------
bench_urls = {}
for p in papers:
    if p["kind"] == "benchmark" and p["url"]:
        bench_urls[norm(p["title"])] = p["url"]
ds_map = {}
for r in res_rows:
    raw = clean(r.get("Benchmarks/Datasets", ""))
    if not raw:
        continue
    for part in [x.strip() for x in raw.replace("|", ";").split(";") if x.strip()]:
        key = norm(re.sub(r"\s*\([^)]*\)\s*$", "", part))
        if not key:
            continue
        d = ds_map.setdefault(key, {"name": re.sub(r"\s*\([^)]*\)\s*$", "", part), "people": [], "url": ""})
        if r["Name"] not in d["people"]:
            d["people"].append(r["Name"])
        if not d["url"]:
            for bk, bu in bench_urls.items():
                if key in bk or bk in key:
                    d["url"] = bu
                    break
datasets = sorted(ds_map.values(), key=lambda d: (-len(d["people"]), d["name"].lower()))

# ---- enrich datasets from dataset_info.json (web-verified url/desc/year).
# Web-verified official URL wins over the manifest heuristic match above.
DS_INFO = os.path.join(SELF_DIR, "dataset_info.json")
n_ds_enriched = 0
if os.path.exists(DS_INFO):
    ds_info = {norm(e["name"]): e for e in json.load(open(DS_INFO, encoding="utf-8"))["datasets"]}
    for d in datasets:
        e = ds_info.get(norm(d["name"]))
        if e:
            if e.get("url"):
                d["url"] = e["url"]
            d["desc"] = e.get("desc", "")
            d["year"] = e.get("year", "")
            d["tags"] = e.get("tags", [])
            n_ds_enriched += 1

# ---------- flag papers that ARE one of our tracked datasets (2026-07-04) ----
# A paper is flagged when a tracked dataset's name appears as a whole-token run
# in its title (e.g. "The WMDP Benchmark…" -> WMDP). Longest name wins.
_dset_names = sorted(((norm(d["name"]), d["name"]) for d in datasets
                      if len(norm(d["name"])) >= 3),
                     key=lambda x: -len(x[0]))
n_paper_datasets = 0
for pap in papers:
    _nt = " " + norm(pap["title"]) + " "
    pap["dataset"] = ""
    for _dn, _orig in _dset_names:
        if " " + _dn + " " in _nt:
            pap["dataset"] = _orig
            n_paper_datasets += 1
            break

# ---------- policies / frontier safety frameworks (manifest, source_type=policy) ----------
# The Policy tab (METR FSP-style index) groups published safety policies by
# developer. Source of truth is the RAG manifest, same as papers; a doc appears
# here iff its vault frontmatter / csv row has source_type=policy.
# Order matters: first match wins. Distinctive org tokens (METR/FMF by author,
# then org names) are checked before generic framework phrases that several labs
# share — e.g. "frontier safety framework" is used by DeepMind AND G42, so G42's
# own name must be checked first and DeepMind's generic phrase kept last.
POLICY_ORG_RULES = [
    ("METR", ["metr"]),
    ("Frontier Model Forum", ["frontier model forum"]),
    ("Anthropic", ["anthropic", "responsible scaling", "long-term benefit trust",
                   "long term benefit trust", "activating ai safety"]),
    ("OpenAI", ["openai", "preparedness framework"]),
    ("Meta", ["meta advanced ai scaling", "advanced ai scaling framework",
              "meta frontier ai framework"]),
    ("Microsoft", ["microsoft"]),
    ("Amazon", ["amazon"]),
    ("xAI", ["xai", "grok"]),
    ("NVIDIA", ["nvidia"]),
    ("Magic", ["magic agi", "agi readiness"]),
    ("NAVER", ["naver"]),
    ("G42", ["g42"]),
    ("Cohere", ["cohere"]),
    ("Google DeepMind", ["deepmind", "google", "frontier safety framework"]),
]
FRAMEWORK_RE = re.compile(
    r"responsible scaling policy|preparedness framework|frontier safety framework|"
    r"frontier ai framework|advanced ai scaling framework|frontier governance framework|"
    r"frontier ai risk assessment|risk management framework|agi readiness policy|"
    r"frontier model safety framework|secure ai frontier model framework|"
    r"\bai safety framework\b|frontier compliance framework", re.I)
# Titles that are commentary/announcements about policies, not the policy itself —
# forced to kind=commentary even when they contain a framework phrase.
COMMENTARY_RE = re.compile(
    r"^(announcing|activating|introducing|updating|our approach|why |managing |"
    r"key components|common elements|evaluating |ai models can be|"
    r"responsible scaling policies|the long-term benefit trust)", re.I)

def infer_policy_org(title_hay, tag_hay):
    # Title/author/path is the reliable org signal. Tags are only a fallback:
    # many framework PDFs carry comparison tags naming *other* labs (a DeepMind
    # FSF tagged both "DeepMind" and "Anthropic"), so tag-based org attribution
    # must never override a title match.
    for org, kws in POLICY_ORG_RULES:
        if any(kw in title_hay for kw in kws):
            return org
    for org, kws in POLICY_ORG_RULES:
        if any(kw in tag_hay for kw in kws):
            return org
    return "Other / cross-org"

policies = []
for r in csv.DictReader(open(MANIFEST, encoding="utf-8")):
    if r["source_type"] != "policy":
        continue
    title = clean(r["title"])
    title_hay = (" " + title + " " + clean_author(r["author"])
                 + " " + clean(r.get("relpath", "")) + " ").lower()
    tag_hay = " " + clean(r["tags"]).lower() + " "
    summary = clean(r["summary"])
    if len(summary) > 320:
        summary = summary[:317].rsplit(" ", 1)[0] + "…"
    policies.append({
        "title": title,
        "org": infer_policy_org(title_hay, tag_hay),
        "date": clean(r["published"]),
        "url": clean(r["source_url"]),
        "summary": summary,
        "kind": "commentary" if COMMENTARY_RE.search(title)
                else ("framework" if FRAMEWORK_RE.search(title) else "commentary"),
        "sub": re.sub(r"^\d+[a-z]?_", "", r["subcategory"]).replace("-", " "),
    })
# newest first, then stable-group by org with frameworks ahead of commentary
policies.sort(key=lambda p: p["date"] or "0000", reverse=True)
policies.sort(key=lambda p: (p["org"].lower(), 0 if p["kind"] == "framework" else 1))

extra = {
    "generated": datetime.date.today().isoformat(),
    "papers": papers, "orgGroups": org_groups, "orgs": orgs,
    "conferences": conferences, "fellowships": fellowships, "datasets": datasets,
    "policies": policies,
    "notionFetched": notion.get("fetched", ""),
}
json.dump(extra, open(os.path.join(SELF_DIR, "extra_data.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=0)

print(f"papers: {len(papers)} ({sum(1 for p in papers if p['kind']=='benchmark')} benchmarks) | "
      f"with year: {sum(1 for p in papers if p['date'])} | "
      f"with people-author: {n_paper_authors} | tracked-dataset papers: {n_paper_datasets}")
print(f"orgs: {len(orgs)} in {len(org_groups)} groups | with people: {sum(1 for o in orgs if o['people'])}")
print(f"conferences: {len(conferences)} (notion+csv {sum(1 for c in conferences if c['src']=='notion+csv')}, "
      f"notion-only {sum(1 for c in conferences if c['src']=='notion')}, csv-only {sum(1 for c in conferences if c['src']=='csv')})")
print(f"fellowships: {len(fellowships)} programs ({n_fellow_merged} role-variants merged), "
      f"{sum(len(f['people']) for f in fellowships)} placements | "
      f"notion-enriched: {sum(1 for f in fellowships if f.get('program_full'))}")
print(f"datasets: {len(datasets)} | with url: {sum(1 for d in ds_map.values() if d['url'])} | "
      f"info-enriched: {n_ds_enriched}")
_pf = sum(1 for p in policies if p["kind"] == "framework")
print(f"policies: {len(policies)} ({_pf} frameworks) across "
      f"{len({p['org'] for p in policies})} developers")
