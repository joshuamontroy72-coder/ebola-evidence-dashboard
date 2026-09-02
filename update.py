#!/usr/bin/env python3
"""
Ebola (Bundibugyo) Evidence Dashboard — data pipeline entry point.

Run:  python pipeline/update.py

What it does, in order:
  1. Fetch from every source (Europe PMC, ClinicalTrials.gov, RSS feeds, news).
  2. Classify each item (intervention, species, Bundibugyo/Canada flags).
  3. Apply the inclusion rule (animal research kept only for vaccines) and an
     on-topic relevance guard.
  4. Deduplicate (by DOI / NCT id / URL / title).
  5. Merge with the existing data/evidence.json so history is preserved:
       - `first_seen` (when we first found an item) never changes
       - manual review status is preserved
  6. Enrich new items with Altmetric attention scores (if they have a DOI).
  7. Mark items as reviewed from pipeline/reviewed_ids.txt (curation).
  8. Write data/evidence.json (records + summary counts + metadata).

Designed to run daily via GitHub Actions. Fully functional with no API keys.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))

from classify import classify, passes_inclusion, is_relevant  # noqa: E402
import sources  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "evidence.json"
REVIEWED_FILE = ROOT / "pipeline" / "reviewed_ids.txt"

TODAY = dt.date.today()
NEW_ITEM_DAYS = 21  # items first seen within this many days are tagged "new"

INTERVENTION_LABELS = {
    "vaccine": "Vaccine",
    "monoclonal": "Monoclonal antibody",
    "other_therapeutic": "Other therapeutic",
    "unspecified": "Unspecified",
}

SOURCE_TYPE_LABELS = {
    "journal_article": "Journal article",
    "preprint": "Preprint",
    "clinical_trial": "Clinical trial",
    "news": "News story",
    "outbreak_report": "Outbreak report",
    "guideline": "Guideline / NITAG",
    "press_release": "Press release",
}

# Canonical monitored channels (used by the dashboard's source-coverage panel).
# Order matters — it's the display order.
CHANNELS = [
    "Journals (Europe PMC / PubMed)",
    "Preprints (bioRxiv / medRxiv)",
    "ClinicalTrials.gov",
    "WHO IRIS guidance",
    "WHO Disease Outbreak News",
    "Other guidance (Africa CDC / gov)",
    "News (CBC / STAT / Reuters / …)",
    "Press releases",
]


def channel_of(rec: dict) -> str:
    st = rec.get("source_type", "")
    src = (rec.get("source", "") or "")
    if st == "preprint":
        return "Preprints (bioRxiv / medRxiv)"
    if st == "clinical_trial":
        return "ClinicalTrials.gov"
    if st == "outbreak_report":
        return "WHO Disease Outbreak News"
    if st == "guideline":
        return "WHO IRIS guidance" if ("IRIS" in src or src == "WHO") else "Other guidance (Africa CDC / gov)"
    if st == "press_release":
        return "Press releases"
    if st == "news":
        return "News (CBC / STAT / Reuters / …)"
    return "Journals (Europe PMC / PubMed)"


def log(msg: str) -> None:
    print(f"[update] {msg}", flush=True)


def record_key(rec: dict) -> str:
    """Dedup key: prefer DOI, then NCT id, then URL, then title."""
    if rec.get("doi"):
        return "doi:" + rec["doi"].lower()
    nct = rec.get("extra", {}).get("nct_id")
    if nct:
        return "nct:" + nct.lower()
    if rec.get("url"):
        # strip tracking noise
        u = re.sub(r"[?#].*$", "", rec["url"].lower()).rstrip("/")
        return "url:" + u
    return "title:" + re.sub(r"\W+", "", (rec.get("title", "")).lower())[:80]


def finalize(rec: dict) -> dict:
    """Trim + add display fields."""
    rec["summary"] = (rec.get("summary") or "").strip()
    if len(rec["summary"]) > 600:
        rec["summary"] = rec["summary"][:597].rstrip() + "…"
    rec["intervention_labels"] = [
        INTERVENTION_LABELS.get(i, i) for i in rec.get("intervention", [])
    ]
    rec["source_type_label"] = SOURCE_TYPE_LABELS.get(
        rec.get("source_type", ""), rec.get("source_type", "")
    )
    rec["channel"] = channel_of(rec)
    # is_new
    fs = rec.get("first_seen")
    try:
        rec["is_new"] = (TODAY - dt.date.fromisoformat(fs)).days <= NEW_ITEM_DAYS
    except Exception:
        rec["is_new"] = True
    return rec


def load_history() -> dict:
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            return {r["id"]: r for r in data.get("records", [])}
        except Exception as e:  # noqa: BLE001
            log(f"Could not read existing data ({e}); starting fresh.")
    return {}


def load_reviewed_ids() -> set[str]:
    if REVIEWED_FILE.exists():
        ids = set()
        for line in REVIEWED_FILE.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                ids.add(line)
        return ids
    return set()


def main() -> int:
    log(f"Run start {dt.datetime.now().isoformat(timespec='seconds')}")

    # 1. fetch
    raw: list[dict] = []
    source_status: dict[str, int] = {}
    for name, fetcher in sources.ALL_FETCHERS:
        try:
            items = fetcher()
            raw.extend(items)
            source_status[name] = len(items)
        except Exception as e:  # noqa: BLE001
            log(f"! fetcher '{name}' failed: {e}")
            source_status[name] = -1

    log(f"Fetched {len(raw)} raw items")

    # 2-4. classify, filter, dedup
    by_key: dict[str, dict] = {}
    dropped_animal = dropped_offtopic = 0
    for rec in raw:
        if not rec.get("title"):
            continue
        classify(rec)
        if not is_relevant(rec):
            dropped_offtopic += 1
            continue
        if not passes_inclusion(rec):
            dropped_animal += 1
            continue
        rec["id"] = sources.stable_id(record_key(rec))
        key = record_key(rec)
        # keep the richest record if duplicates within this run
        if key not in by_key or len(rec.get("summary", "")) > len(
            by_key[key].get("summary", "")
        ):
            # preserve id stability across dup choice
            rec["id"] = sources.stable_id(key)
            by_key[key] = rec

    fresh = list(by_key.values())
    log(
        f"After classify/filter: {len(fresh)} kept "
        f"(dropped {dropped_animal} animal-therapeutic, {dropped_offtopic} off-topic)"
    )

    # 5. merge with history
    history = load_history()
    merged: dict[str, dict] = dict(history)
    new_count = 0
    today_iso = TODAY.isoformat()

    for rec in fresh:
        rid = rec["id"]
        if rid in merged:
            prev = merged[rid]
            rec["first_seen"] = prev.get("first_seen", today_iso)
            rec["reviewed"] = prev.get("reviewed", False)
            # keep altmetric unless we refresh below
            for k in ("altmetric_score", "altmetric_url", "altmetric_reads",
                      "altmetric_mentions"):
                if k in prev and k not in rec:
                    rec[k] = prev[k]
        else:
            rec["first_seen"] = today_iso
            rec["reviewed"] = False
            new_count += 1
        merged[rid] = rec

    log(f"New items this run: {new_count}; total in corpus: {len(merged)}")

    # 6. altmetric enrichment — new items + a refresh of recent ones
    to_enrich = [
        r for r in merged.values()
        if r.get("doi") and (
            "altmetric_score" not in r
            or _recent(r.get("first_seen"), 30)
        )
    ]
    log(f"Altmetric: enriching {len(to_enrich)} records with DOIs")
    sources.enrich_altmetric(to_enrich)

    # 7. curation: mark reviewed
    reviewed_ids = load_reviewed_ids()
    for rid in reviewed_ids:
        if rid in merged:
            merged[rid]["reviewed"] = True

    # 8. finalize + write
    records = [finalize(r) for r in merged.values()]
    records.sort(key=lambda r: (r.get("published_date") or "", r.get("first_seen") or ""),
                 reverse=True)

    # Per-channel view of what THIS run's fetch produced (before merge), so a
    # silently-empty source is visible on the dashboard's coverage panel.
    run_by_channel: dict[str, int] = {c: 0 for c in CHANNELS}
    for r in fresh:
        run_by_channel[channel_of(r)] = run_by_channel.get(channel_of(r), 0) + 1
    fetcher_errors = [name for name, n in source_status.items() if n == -1]

    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "record_count": len(records),
        "new_last_run": new_count,
        "counts": _counts(records),
        "source_status": source_status,
        "coverage": {
            "channels": CHANNELS,
            "run_counts": run_by_channel,
            "fetcher_errors": fetcher_errors,
        },
        "records": records,
    }

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Wrote {DATA_FILE} ({len(records)} records)")
    return 0


def _recent(iso: str | None, days: int) -> bool:
    try:
        return (TODAY - dt.date.fromisoformat(iso)).days <= days
    except Exception:
        return False


def _counts(records: list[dict]) -> dict:
    def tally(key_fn):
        out: dict[str, int] = {}
        for r in records:
            for v in key_fn(r):
                out[v] = out.get(v, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: kv[1], reverse=True))

    return {
        "by_type": tally(lambda r: [r.get("source_type_label", "")]),
        "by_channel": tally(lambda r: [r.get("channel", "")]),
        "by_intervention": tally(lambda r: r.get("intervention_labels", [])),
        "by_species": tally(lambda r: [r.get("species", "na")]),
        "bundibugyo": sum(1 for r in records if r.get("bundibugyo")),
        "canadian": sum(1 for r in records if r.get("canadian")),
        "new": sum(1 for r in records if r.get("is_new")),
        "with_altmetric": sum(1 for r in records if r.get("altmetric_score")),
    }


if __name__ == "__main__":
    raise SystemExit(main())
