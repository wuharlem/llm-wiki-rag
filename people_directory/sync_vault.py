#!/usr/bin/env python3
"""Sync directory outputs into the vault (05_Resources/05a_Educational/):

1. ai-safety-people-directory.html — static copy of the artifact HTML (not indexed).
2. AI-Safety-Conferences-Full-Roster-135.md — regenerated deterministically from
   notion_conferences.json; only rewritten when content actually changes (i.e.
   after a manual re-scrape of the Notion conference DB).

Run AFTER gen_directory.py. Prints one line per target: synced / unchanged.
IMPORTANT for agents: if the roster md line says "synced", the vault content
changed — call rebuild_index and append_log (kind=note) afterwards. The HTML
copy never requires a rebuild (html is not indexed).
"""
import json, os, glob, sys

SELF_DIR = os.path.dirname(os.path.abspath(__file__))

def find_vault_dir():
    parts = SELF_DIR.split(os.sep)
    roots = []
    if "mnt" in parts:
        roots.append(os.sep.join(parts[: parts.index("mnt") + 1]))
    roots.append(os.path.expanduser("~/Desktop"))
    for root in roots:
        hits = glob.glob(os.path.join(root, "**", "05_Resources", "05a_Educational"), recursive=True)
        hits = [h for h in hits if "/_trash/" not in h]
        if hits:
            return sorted(hits, key=len)[0]
    return None

DEST = find_vault_dir()
if not DEST:
    sys.exit("ERROR: could not locate vault 05_Resources/05a_Educational under the session mount.")

def sync_bytes(content: bytes, dest_path: str, label: str) -> bool:
    old = open(dest_path, "rb").read() if os.path.exists(dest_path) else None
    if old == content:
        print(f"{label}: unchanged")
        return False
    open(dest_path, "wb").write(content)
    print(f"{label}: synced -> {dest_path}")
    return True

# ---- 1. HTML copy ----
html_src = os.path.join(SELF_DIR, "ai-safety-people-directory.html")
sync_bytes(open(html_src, "rb").read(), os.path.join(DEST, "ai-safety-people-directory.html"), "html")

# ---- 2. Conference roster md (deterministic from notion_conferences.json) ----
d = json.load(open(os.path.join(SELF_DIR, "notion_conferences.json"), encoding="utf-8"))
confs, fetched, n = d["conferences"], d.get("fetched", ""), d.get("count", len(d["conferences"]))
TYPES = [("academic", "Academic (ML/security venues & workshops)"),
         ("industry", "Industry & enterprise security"),
         ("governance", "Governance, policy & summits"),
         ("community", "Community, EA & alignment ecosystem"),
         ("mixed", "Mixed / cross-cutting"),
         ("", "Untyped")]

def esc(s):
    return str(s or "").replace("|", "∕").strip()

L = []
L.append("""---
title: "AI Safety Conferences & Symposia — Full Roster ({n})"
source: Notion database "AI Safety Conferences & Symposia"
author: HARLEM (curated)
created: {fetched}
description: Full snapshot of the {n}-row Notion conference database (fetched {fetched}) — academic ML/security venues, industry summits, governance forums, and alignment-community events tracked for the AI-security researcher roster, with year, location, focus areas, join priority, and roster-participant counts.
tags:
- llm-security
- background-reading
concepts: []
risk_category:
- misuse
- misalignment
source_type: reference
---

# AI Safety Conferences & Symposia — Full Roster ({n})

Source: Notion database "AI Safety Conferences & Symposia" (snapshot fetched {fetched}; the Notion connector cannot query rows on this plan, so this page is refreshed only by manual re-scrape).
Total: **{n} events** across academic ({a}) · industry ({i}) · governance ({g}) · community ({c}) · mixed ({m}).

Companion pages: [[AI-Security-Orgs-Full-Roster-200]] · [[AI-Security-Researchers-to-Follow]]. The `Conferences` column of the researchers CSV records who appeared where (with roles); the tabbed "AI Safety Directory" Cowork artifact merges both views.
""".format(n=n, fetched=fetched,
           a=sum(1 for c in confs if c.get("Type", "") == "academic"),
           i=sum(1 for c in confs if c.get("Type", "") == "industry"),
           g=sum(1 for c in confs if c.get("Type", "") == "governance"),
           c=sum(1 for c in confs if c.get("Type", "") == "community"),
           m=sum(1 for c in confs if c.get("Type", "") == "mixed")))
for tval, tlabel in TYPES:
    rows = [c for c in confs if c.get("Type", "") == tval]
    if not rows:
        continue
    rows.sort(key=lambda c: (str(c.get("Year", "")), c.get("Name", "")), reverse=True)
    L.append(f"\n## {tlabel} ({len(rows)})\n")
    L.append("| Event | Year | Location | Focus | Priority | Roster ppl | Why it matters |")
    L.append("|---|---|---|---|---|---|---|")
    for c in rows:
        name = esc(c.get("Name"))
        if c.get("URL"):
            name = f"[{name}]({c['URL']})"
        focus = ", ".join(c.get("Focus area", []) or ([] if not c.get("Focus") else [c["Focus"]]))
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            name, esc(c.get("Year")), esc(c.get("Location")), esc(focus),
            esc(c.get("Join priority")), esc(c.get("Roster participants")), esc(c.get("Recommendation"))))
    notes = [(c.get("Name"), c["Notes"]) for c in rows if c.get("Notes")]
    if notes:
        L.append("\n**Notes:**")
        for nm, txt in notes:
            L.append(f"- **{esc(nm)}**: {esc(txt)}")
md = ("\n".join(L) + "\n").encode("utf-8")

# Roster filename tracks the row count; if the count changed, move the old file's
# name forward (never leave two rosters). Find any existing roster in the vault.
existing = sorted(glob.glob(os.path.join(DEST, "AI-Safety-Conferences-Full-Roster-*.md")))
dest_md = os.path.join(DEST, f"AI-Safety-Conferences-Full-Roster-{n}.md")
for old in existing:
    if old != dest_md:
        os.rename(old, dest_md)  # rename in place; content overwritten next
changed = sync_bytes(md, dest_md, "conference roster md")
if changed:
    print("NOTE: roster changed -> run rebuild_index and append_log(kind=note) to keep the RAG index and log current.")
