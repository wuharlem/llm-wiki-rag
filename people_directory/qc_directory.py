#!/usr/bin/env python3
"""qc_directory.py — mechanical data-quality checker for the AI Safety People Directory.

Deterministic, stdlib-only. Reads the *derived* JSON products (people.json,
extra_data.json, org_categories.json, arxiv_titles.json) and reports internal
integrity + structural-link problems across ALL tabs — people, organizations,
papers, policy, conferences, datasets, fellowships. It NEVER edits anything — it
only reports. Fixes belong at the source of truth (see WORKFLOW.md); this script
tells you what to fix.

Companion to the weekly `weekly-ai-safety-directory-qc` scheduled task, which
runs this for Bundle A (internal integrity) and Bundle B-structural (link
sanity), then layers web-based staleness/coverage checks on top.

Usage:
    python3 qc_directory.py            # human-readable report
    python3 qc_directory.py --json     # machine-readable JSON

    python3 qc_directory.py --metrics  # also append a row to qc_metrics.csv

Exit code: 0 = all green, 1 = one or more red flags, 2 = could not load inputs.

Placeholder markers (the "unhomed 88" from the 2026-07-01 fellowship scan) are
the exact category/org strings the vault researchers file assigns to those
people; they flow verbatim through parse_raw.py into people.json. They are NOT
defined in parse_raw.py — their source of truth is the vault .md text. The risk
this creates: if that vault text is ever reworded, the exact-match below would
silently report 0 placeholders while 82 people stay unhomed. `_placeholder_drift`
(below) guards against exactly that by cross-checking a fuzzy match.
"""
import json
import os
import re
import sys
import csv
import datetime
import collections

HERE = os.path.dirname(os.path.abspath(__file__))

PLACEHOLDER_CATEGORY = "🎓 Fellowship & Program Involvement (2026-07-01)"
PLACEHOLDER_ORG = "New additions from the fellowship scan (🆕 2026-07-01)"
# Fuzzy fallback for the drift guard: matches the *intent* of the markers above
# without depending on their exact wording, so a reworded vault string can't make
# unhomed people vanish from the report silently.
PLACEHOLDER_FUZZY = re.compile(r"fellowship\s*scan|2026-07-01", re.IGNORECASE)

# Append-only trend log. Written only with --metrics so the plain report stays
# side-effect-free. The regression guard reads its last row.
METRICS_FILE = "qc_metrics.csv"
METRICS_COLS = ["checked_at", "generated", "people", "orgs", "papers",
                "confs", "fellowships", "datasets", "policies",
                "placeholder_people", "n_red", "n_findings"]

# staleness: the directory refresh is daily, so the derived snapshot should
# never be more than a few days old when QC runs. Weekly cadence => 8 days.
STALE_DAYS = 8


def _load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return json.load(fh)


def _last_metrics():
    """Return the placeholder_people count from the last qc_metrics.csv row,
    or None if the log doesn't exist / is empty / unreadable. Used by the
    regression guard — never raises."""
    path = os.path.join(HERE, METRICS_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            return None
        return int(rows[-1]["placeholder_people"])
    except Exception:  # noqa: BLE001
        return None


def _write_metrics(result):
    """Append one trend row. Creates the file with a header if missing."""
    path = os.path.join(HERE, METRICS_FILE)
    c = result["counts"]
    row = {
        "checked_at": result["checked_at"],
        "generated": result["generated"],
        "people": c.get("people.json", ""),
        "orgs": c.get("extra.orgs", ""),
        "papers": c.get("extra.papers", ""),
        "confs": c.get("extra.conferences", ""),
        "fellowships": c.get("extra.fellowships", ""),
        "datasets": c.get("extra.datasets", ""),
        "policies": c.get("extra.policies", ""),
        "placeholder_people": result["placeholder_people"],
        "n_red": result["n_red"],
        "n_findings": result["n_findings"],
    }
    exists = os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=METRICS_COLS)
        if not exists:
            w.writeheader()
        w.writerow(row)


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _people_refs(entry):
    """conference/fellowship .people are [{'n': name, ...}]; org/dataset .people
    are [name, ...]. Return a flat list of referenced names, both forms."""
    out = []
    for pe in entry.get("people") or []:
        if isinstance(pe, dict):
            n = pe.get("n") or pe.get("name")
            if n:
                out.append(n)
        elif isinstance(pe, str):
            out.append(pe)
    return out


def _days_old(datestr):
    try:
        d = datetime.date.fromisoformat(datestr[:10])
        return (datetime.date.today() - d).days
    except Exception:
        return None


def run():
    findings = []  # each: (severity, code, message, list-of-items)

    def flag(sev, code, msg, items=None):
        findings.append({"severity": sev, "code": code, "message": msg,
                         "items": items or []})

    try:
        P = _load("people.json")
        E = _load("extra_data.json")
        OC = _load("org_categories.json")
    except Exception as exc:  # noqa: BLE001
        print(f"qc_directory: could not load inputs: {exc}", file=sys.stderr)
        return 2
    try:
        AT = _load("arxiv_titles.json")
    except Exception:
        AT = {}

    names = {p.get("name", "").strip() for p in P if p.get("name")}
    names_norm = {_norm(p.get("name", "")): p.get("name", "") for p in P}

    # --- A1. Unhomed placeholder people ----------------------------------
    ph = [p["name"] for p in P
          if p.get("category") == PLACEHOLDER_CATEGORY
          or p.get("org") == PLACEHOLDER_ORG]
    if ph:
        flag("red", "placeholder_people",
             f"{len(ph)} people still carry the 2026-07-01 fellowship-scan "
             f"placeholder category/org — re-home to a real org/category in "
             f"the vault researchers file, then regenerate.", sorted(ph))

    # --- A1b. Marker-drift guard (hardening) -----------------------------
    # Cross-check the exact-match count against a fuzzy match. If the fuzzy
    # match finds MORE unhomed people than the exact markers, the vault text
    # was reworded and PLACEHOLDER_CATEGORY/ORG have gone stale — the exact
    # count is silently under-reporting. Fail loud instead.
    fuzzy_ph = [p["name"] for p in P
                if PLACEHOLDER_FUZZY.search(p.get("category", "") or "")
                or PLACEHOLDER_FUZZY.search(p.get("org", "") or "")]
    if len(fuzzy_ph) > len(ph):
        drifted = sorted(set(fuzzy_ph) - set(ph))
        flag("red", "placeholder_marker_drift",
             f"{len(fuzzy_ph)} people match the fuzzy placeholder pattern but "
             f"only {len(ph)} match the exact PLACEHOLDER_CATEGORY/ORG strings "
             f"— the vault marker text likely changed. Update the constants in "
             f"qc_directory.py to match the vault researchers file.", drifted)

    # --- A1c. Placeholder regression guard -------------------------------
    # The upstream policy (WORKFLOW.md) is that people are NEVER injected as
    # placeholders anymore — the 2026-07-01 batch is legacy and only shrinks.
    # If the count grew since the last recorded run, something re-injected
    # placeholders; surface it as a red flag so it can't accumulate silently.
    prev = _last_metrics()
    if prev is not None and len(ph) > prev:
        flag("red", "placeholder_regression",
             f"placeholder_people rose {prev} → {len(ph)} since the last "
             f"metrics-logged run. People should only ever be re-homed, never "
             f"re-injected — check what added them (see WORKFLOW.md upstream "
             f"policy).")

    # --- A2. Empty required fields ---------------------------------------
    no_org = [p["name"] for p in P if not p.get("org")]
    no_blurb = [p["name"] for p in P if not p.get("blurb")]
    no_focus = [p["name"] for p in P if not p.get("focus")]
    if no_org:
        flag("red", "missing_org", f"{len(no_org)} people have no org.", no_org)
    if no_blurb:
        flag("red", "missing_blurb",
             f"{len(no_blurb)} people have no blurb.", no_blurb)
    if no_focus:
        # focus is often inferred/optional; report as amber, not red.
        flag("amber", "missing_focus",
             f"{len(no_focus)} people have no focus field.", no_focus)

    # --- A3. Duplicate people --------------------------------------------
    exact = [n for n, c in collections.Counter(
        p.get("name", "").strip() for p in P).items() if c > 1 and n]
    if exact:
        flag("red", "duplicate_people",
             f"{len(exact)} exact-duplicate person name(s).", exact)
    # near-dup: same normalized name, different surface form
    norm_groups = collections.defaultdict(set)
    for p in P:
        norm_groups[_norm(p.get("name", ""))].add(p.get("name", "").strip())
    near = ["/".join(sorted(v)) for k, v in norm_groups.items()
            if k and len(v) > 1]
    if near:
        flag("amber", "near_duplicate_people",
             f"{len(near)} name(s) collapse to the same normalized form.", near)

    # --- A4. Cross-tab dangling references -------------------------------
    # A name referenced by an org/dataset/conference/fellowship that has no
    # matching person page. Matches the generator's exact-name join, so a
    # dangling ref = a chip that renders as dead text.
    dangling = collections.defaultdict(list)
    for section in ("orgs", "datasets", "conferences", "fellowships"):
        for entry in E.get(section, []):
            for ref in _people_refs(entry):
                if ref.strip() and ref.strip() not in names \
                        and _norm(ref) not in names_norm:
                    dangling[section].append(f"{ref}  (in {entry.get('name')})")
    total_dangling = sum(len(v) for v in dangling.values())
    if total_dangling:
        items = [f"[{s}] {x}" for s, xs in dangling.items() for x in xs]
        flag("amber", "dangling_people_refs",
             f"{total_dangling} people referenced by orgs/datasets/confs/"
             f"fellowships that don't exist as person pages (dead chips).",
             items)

    # --- A5. Count reconciliation ----------------------------------------
    recon = {
        "people.json": len(P),
        "extra.papers": len(E.get("papers", [])),
        "extra.orgs": len(E.get("orgs", [])),
        "extra.conferences": len(E.get("conferences", [])),
        "extra.fellowships": len(E.get("fellowships", [])),
        "extra.datasets": len(E.get("datasets", [])),
        "extra.policies": len(E.get("policies", [])),
        "org_categories": len(OC),
    }
    # orgs present on people but absent from the org_categories map
    people_orgs = {p.get("org", "").strip() for p in P if p.get("org")}
    uncat = sorted(o for o in people_orgs
                   if o and o != PLACEHOLDER_ORG and o not in OC)
    if uncat:
        flag("amber", "orgs_not_categorized",
             f"{len(uncat)} orgs appear on people pages but are missing from "
             f"org_categories.json.", uncat)

    # --- B1. URL structural sanity ---------------------------------------
    bad_urls = []
    def _check_url(u, where):
        if not u:
            return
        if not re.match(r"^https?://", u.strip()):
            bad_urls.append(f"{where}: malformed url {u!r}")
    for p in P:
        for k in ("x", "site", "linkedin"):
            _check_url(p.get(k), f"person {p.get('name')} .{k}")
    for pap in E.get("papers", []):
        _check_url(pap.get("url"), f"paper {pap.get('title')}")
    for d in E.get("datasets", []):
        _check_url(d.get("url"), f"dataset {d.get('name')}")
    # conference URLs pointing at a personal profile / PDF / social are the
    # 2026-07-04 class of bug (e.g. x.com/geoffreyirving as a venue link).
    conf_suspect = []
    SUSPECT_HOST = re.compile(r"(x\.com|twitter\.com|linkedin\.com|/cv|\.pdf$)",
                              re.I)
    for c in E.get("conferences", []):
        u = c.get("url") or ""
        if u and SUSPECT_HOST.search(u):
            conf_suspect.append(f"{c.get('name')}: {u}")
        _check_url(u, f"conf {c.get('name')}")
    if bad_urls:
        flag("red", "malformed_urls",
             f"{len(bad_urls)} malformed URL(s).", bad_urls)
    if conf_suspect:
        flag("amber", "suspect_conference_urls",
             f"{len(conf_suspect)} conference URL(s) point at a profile/PDF/"
             f"social host rather than a venue page — verify.", conf_suspect)

    # --- B2. arXiv id -> title pairing sanity ----------------------------
    # person.papers[].u that is an arxiv link whose id is not in the cache is
    # fine (degrades to a Scholar link) but worth surfacing so the cache can be
    # extended with verified pairs.
    arxiv_re = re.compile(r"arxiv\.org/(?:abs|pdf)/([\d.]+)", re.I)
    missing_ids = set()
    for p in P:
        for pp in p.get("papers") or []:
            m = arxiv_re.search(pp.get("u") or "")
            if m and m.group(1) not in AT:
                missing_ids.add(m.group(1))
    if missing_ids:
        flag("info", "arxiv_ids_uncached",
             f"{len(missing_ids)} arXiv id(s) on people cards not in "
             f"arxiv_titles.json (safe; extend cache with verified pairs).",
             sorted(missing_ids))

    # --- D. Per-tab integrity: orgs / papers / policies / conferences ----
    today = datetime.date.today()
    this_year = today.year

    def _dups(items, keyfn, label, code):
        c = collections.Counter(keyfn(x) for x in items if keyfn(x))
        d = [k for k, n in c.items() if n > 1]
        if d:
            flag("amber", code, f"{len(d)} duplicate {label}.", d)

    def _missing(items, field, label, code, sev="red", namefn=None):
        namefn = namefn or (lambda x: x.get("name") or x.get("title") or "?")
        miss = [namefn(x) for x in items if not x.get(field)]
        if miss:
            flag(sev, code, f"{len(miss)} {label} missing {field}.", miss)

    def _future(items, label, code, namefn=None):
        namefn = namefn or (lambda x: x.get("name") or x.get("title") or "?")
        fut = []
        for x in items:
            d = _days_old(x.get("date", ""))
            if d is not None and d < -3:  # >3 days in the future = likely typo
                fut.append(f"{namefn(x)} ({x.get('date')})")
        if fut:
            flag("amber", code, f"{len(fut)} {label} dated in the future.", fut)

    # Organizations tab
    orgs = E.get("orgs", [])
    valid_groups = set(E.get("orgGroups", []))
    _dups(orgs, lambda o: (o.get("name") or "").strip().lower(),
          "org names", "duplicate_orgs")
    bad_group = [f"{o.get('name')} → {o.get('group')!r}" for o in orgs
                 if o.get("group") and o.get("group") not in valid_groups]
    if bad_group:
        flag("red", "org_group_invalid",
             f"{len(bad_group)} org(s) whose group is not one of the "
             f"{len(valid_groups)} orgGroups (breaks tab grouping).", bad_group)
    _missing(orgs, "group", "orgs", "org_missing_group")

    # Papers tab
    papers = E.get("papers", [])
    _missing(papers, "title", "papers", "paper_missing_title")
    _missing(papers, "url", "papers", "paper_missing_url")
    _missing(papers, "date", "papers", "paper_missing_date", sev="amber",
             namefn=lambda x: x.get("title", "?"))
    _dups(papers, lambda p: _norm(p.get("title", "")), "paper titles",
          "duplicate_papers")
    _future(papers, "papers", "paper_future_date",
            namefn=lambda x: x.get("title", "?"))

    # Policy tab
    policies = E.get("policies", [])
    _missing(policies, "title", "policies", "policy_missing_title")
    _missing(policies, "url", "policies", "policy_missing_url")
    _missing(policies, "date", "policies", "policy_missing_date", sev="amber",
             namefn=lambda x: x.get("title", "?"))
    _missing(policies, "org", "policies", "policy_missing_org", sev="amber",
             namefn=lambda x: x.get("title", "?"))
    _dups(policies, lambda p: _norm(p.get("title", "")), "policy titles",
          "duplicate_policies")
    unattr = [p.get("title") for p in policies
              if p.get("org") in ("Other / cross-org", "Other", "")]
    if unattr:
        flag("info", "policy_org_unattributed",
             f"{len(unattr)} policy entries fell to the 'Other / cross-org' "
             f"org bucket — check POLICY_ORG_RULES if a lab is misfiled.",
             unattr)

    # Conferences tab
    confs = E.get("conferences", [])
    _missing(confs, "url", "conferences", "conf_missing_url", sev="amber")
    _dups(confs, lambda c: (c.get("name") or "").strip().lower(),
          "conference names", "duplicate_confs")
    no_year = [c.get("name") for c in confs if not c.get("year")]
    if no_year:
        flag("info", "conf_missing_year",
             f"{len(no_year)} conference(s) with no year.", no_year)
    # NB: past-year conferences are kept deliberately (tracked series continuity),
    # so staleness of a *future/current* conference is judged in the task's web
    # bundle, not flagged mechanically here.

    # --- C0. Snapshot staleness (mechanical part of staleness bundle) ----
    gen = E.get("generated") or E.get("notionFetched") or ""
    age = _days_old(gen)
    if age is None:
        flag("amber", "no_generated_date",
             "extra_data.json has no parseable 'generated' date.")
    elif age > STALE_DAYS:
        flag("red", "stale_snapshot",
             f"Directory snapshot is {age} days old (generated {gen}); the "
             f"daily refresh may be failing.")

    reds = [f for f in findings if f["severity"] == "red"]
    result = {
        "generated": gen,
        "checked_at": datetime.date.today().isoformat(),
        "counts": recon,
        "placeholder_people": len(ph),
        "n_findings": len(findings),
        "n_red": len(reds),
        "findings": findings,
    }
    return result


def _print_human(result):
    if isinstance(result, int):
        return result
    print(f"AI Safety Directory — mechanical QC  ({result['checked_at']})")
    print(f"snapshot generated: {result['generated']}")
    c = result["counts"]
    print("counts: " + ", ".join(f"{k}={v}" for k, v in c.items()))
    print(f"placeholder/unhomed people: {result['placeholder_people']}")
    print()
    if not result["findings"]:
        print("ALL GREEN — no mechanical issues.")
        return 0
    order = {"red": 0, "amber": 1, "info": 2}
    for f in sorted(result["findings"], key=lambda x: order.get(x["severity"], 9)):
        print(f"[{f['severity'].upper()}] {f['code']}: {f['message']}")
        for it in f["items"][:25]:
            print(f"    - {it}")
        if len(f["items"]) > 25:
            print(f"    ... and {len(f['items']) - 25} more")
    print()
    print(f"{result['n_red']} red flag(s), {result['n_findings']} finding(s) total.")
    return 1 if result["n_red"] else 0


def main():
    result = run()
    if isinstance(result, int):
        return result
    if "--metrics" in sys.argv:
        try:
            _write_metrics(result)
        except Exception as exc:  # noqa: BLE001 — never let logging fail the run
            print(f"qc_directory: metrics write failed: {exc}", file=sys.stderr)
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 1 if result["n_red"] else 0
    return _print_human(result)


if __name__ == "__main__":
    sys.exit(main())
