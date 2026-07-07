#!/usr/bin/env python3
"""regen_guard.py — event-driven short-circuit for the directory refresh.

The directory refresh runs daily, but its inputs (the vault researchers file,
the org roster, the RAG manifest, the conferences snapshot, and a couple of
caches) change only every few days. Regenerating unconditionally bumps the
snapshot date and rewrites the artifact every day for no reason — daily git
noise and misleading "fresh" timestamps on unchanged data.

This guard mirrors the rebuild_index debounce (source_state.json): it
fingerprints the pipeline inputs and lets the task skip the expensive
regenerate + artifact-update when nothing changed.

Two modes:
    python3 regen_guard.py check    # compare inputs to stored fingerprint
                                     #   exit 0 = CHANGED (run the pipeline)
                                     #   exit 3 = UNCHANGED (skip)
                                     #   exit 0 also if no fingerprint yet
    python3 regen_guard.py commit   # store the current fingerprint
                                     #   (call AFTER a successful regeneration)

Fingerprints are content hashes (sha1 of file bytes), so a touch without an
edit does not count as a change. Missing inputs are recorded as the sentinel
"absent" rather than failing — a file appearing/disappearing is itself a change.

Never edits any data file. State lives in `.regen_state.json` next to this
script (git-ignored territory — it is machinery, not a derived product).
"""
import glob
import hashlib
import json
import os
import sys

SELF_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SELF_DIR, ".regen_state.json")


def find_file(pattern):
    """Same resolution order as parse_extra.py::find_file (single source of the
    convention: sandbox mount root, then ~/Desktop, then ~/Documents)."""
    parts = SELF_DIR.split(os.sep)
    roots = []
    if "mnt" in parts:
        roots.append(os.sep.join(parts[: parts.index("mnt") + 1]))
    roots += [os.path.expanduser("~/Desktop"), os.path.expanduser("~/Documents")]
    for root in roots:
        hits = glob.glob(os.path.join(root, "**", pattern), recursive=True)
        hits = [h for h in hits
                if "/_index/" not in h and "/_trash/" not in h
                and "/.claude/" not in h]
        if hits:
            return sorted(hits, key=len)[0]
    return None


# Inputs the pipeline reads. Vault files are located by glob; local snapshots/
# caches are addressed directly. Order is irrelevant — we hash a sorted dict.
def _input_paths():
    paths = {}
    for label, pat in [
        ("researchers_md", "AI-Security-Researchers-to-Follow.md"),
        ("researchers_csv", "AI-Security-Researchers-to-Follow.csv"),
        ("orgs_roster", "AI-Security-Orgs-Full-Roster-200.md"),
        ("manifest", "manifest.csv"),
    ]:
        paths[label] = find_file(pat)
    for label, name in [
        ("notion_conferences", "notion_conferences.json"),
        ("arxiv_titles", "arxiv_titles.json"),
        ("dataset_info", "dataset_info.json"),
    ]:
        p = os.path.join(SELF_DIR, name)
        paths[label] = p if os.path.exists(p) else None
    return paths


def _fingerprint():
    fp = {}
    for label, path in sorted(_input_paths().items()):
        if not path or not os.path.exists(path):
            fp[label] = "absent"
            continue
        h = hashlib.sha1()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        fp[label] = h.hexdigest()
    return fp


def _load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def main(argv):
    mode = argv[1] if len(argv) > 1 else "check"
    if mode not in ("check", "commit"):
        print("usage: regen_guard.py [check|commit]", file=sys.stderr)
        return 2

    current = _fingerprint()

    if mode == "commit":
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump({"fingerprint": current}, fh, indent=1, sort_keys=True)
        print("regen_guard: fingerprint committed")
        return 0

    # mode == check
    prev = _load_state()
    if prev is None or prev.get("fingerprint") != current:
        if prev is None:
            print("CHANGED (no prior fingerprint — first run)")
        else:
            changed = [k for k in current
                       if current[k] != prev["fingerprint"].get(k)]
            print("CHANGED: " + ", ".join(sorted(changed)))
        return 0
    print("UNCHANGED — inputs identical to last committed run; safe to skip regen")
    return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
