#!/usr/bin/env python3
"""Weekly Metadata-health trend logger.

Reads health_snapshot.json (written by gen_directory.py on every directory
refresh) and appends a dated row to health_trend.csv. Prints the current
health pills and WARNS if any gap grew vs. the previous distinct logged row —
the cheap regression detector that catches a bad ingest without eyeballing the
Stats tab.

Pure logger: reads the snapshot the refresh task already produced, writes only
files inside people_directory/. Never touches the vault, never regenerates.
Idempotent per day (re-running the same day overwrites that day's row).

Exit codes: 0 = ok / no regression, 2 = a gap grew since the last row,
3 = snapshot missing or stale (> 8 days old).
"""
import json, os, csv, datetime, sys

BASE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(BASE, "health_snapshot.json")
LOG = os.path.join(BASE, "health_trend.csv")

# Column order is fixed; matches the pill labels in gen_directory._corpus_stats.
FIELDS = ["missing author", "missing published date", "missing tags",
          "missing source URL", "missing source_type"]
COLS = ["checked_at", "generated", "nSources"] + FIELDS


def _load_rows():
    if not os.path.exists(LOG):
        return []
    with open(LOG, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_rows(rows):
    with open(LOG, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})


def main():
    today = datetime.date.today().isoformat()
    if not os.path.exists(SNAP):
        print(f"health_trend: no health_snapshot.json at {SNAP} — run gen_directory.py first.")
        return 3
    snap = json.load(open(SNAP, encoding="utf-8"))
    health = snap.get("health", {})
    generated = snap.get("generated", "")

    # staleness guard: snapshot older than 8 days means the refresh pipeline
    # hasn't run recently; log anyway but flag it.
    stale = False
    try:
        age = (datetime.date.today() - datetime.date.fromisoformat(generated)).days
        stale = age > 8
    except Exception:
        age = None

    row = {"checked_at": today, "generated": generated,
           "nSources": snap.get("nSources", "")}
    for k in FIELDS:
        row[k] = health.get(k, "")

    rows = _load_rows()
    prior = rows[-1] if rows else None
    if rows and rows[-1].get("checked_at") == today:
        prior = rows[-2] if len(rows) > 1 else None
        rows[-1] = row  # overwrite same-day
    else:
        rows.append(row)
    _write_rows(rows)

    # report
    print(f"Metadata health @ {today} (snapshot generated {generated}"
          + (f", {age}d old" if age is not None else "") + "):")
    grew = []
    for k in FIELDS:
        cur = health.get(k)
        line = f"  {k:26} {cur}"
        if prior and str(prior.get(k, "")).strip() != "":
            try:
                d = int(cur) - int(prior[k])
                if d > 0:
                    line += f"  ▲ +{d} since {prior.get('checked_at')}"
                    grew.append((k, d))
                elif d < 0:
                    line += f"  ▼ {d}"
            except (TypeError, ValueError):
                pass
        print(line)

    rc = 0
    if stale:
        print(f"WARN: snapshot is {age}d old — directory refresh may not have run; "
              "numbers may lag the live vault.")
        rc = 3
    if grew:
        print("WARN: metadata gaps grew: "
              + ", ".join(f"{k} (+{d})" for k, d in grew)
              + " — likely a recent ingest missing frontmatter.")
        rc = 2
    if not grew and not stale:
        print("OK: no metadata-health regression since the last logged check.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
