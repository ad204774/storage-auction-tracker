"""Completed auctions: visit each auction's page after it closes and record the final price.

Both StorageTreasures ("Final High Bid: $820") and Bid13 ("FINAL PRICE $491") keep the
winning bid on the auction page after it ends. Our own hourly scrape can't see the last
minutes of bidding, so the page is the only reliable source.

Results are kept in data/sold.json (60 days) and published as docs/sold.json.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

KEEP_DAYS = 60
MAX_TRIES = 3


def parse_final(text: str) -> dict:
    """Pull the final price and bid count out of an ended auction page's visible text."""
    out: dict = {}
    m = re.search(r"Final High Bid:?\s*\$\s*([\d,]+(?:\.\d\d)?)", text, re.I) or \
        re.search(r"FINAL PRICE\s*\$\s*([\d,]+(?:\.\d\d)?)", text, re.I)
    if m:
        out["final"] = float(m.group(1).replace(",", ""))
    m = re.search(r"Bids on this unit:?\s*(\d+)", text, re.I)
    if m:
        out["nbids"] = int(m.group(1))
    if re.search(r"auction (?:was |has been )?(?:canceled|cancelled)|\bcancel(?:l)?ed\b", text, re.I) and "final" not in out:
        out["canceled"] = True
    out["ended"] = bool(re.search(r"auction (?:has )?ended|\bENDED\b|FINAL PRICE", text))
    return out


def fetch_final(page, url: str) -> dict:
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_timeout(2_500)
    return parse_final(page.inner_text("body"))


def update(page, seen: dict, path: Path, limit: int = 40, now: datetime | None = None) -> dict:
    """Check up to `limit` recently ended auctions; return the sold archive."""
    now = now or datetime.now(timezone.utc)
    sold: dict = json.loads(path.read_text()) if path.exists() else {}
    todo = []
    for key, v in seen.items():
        end = v.get("ends_at")
        if not end:
            continue
        end = datetime.fromisoformat(end)
        if not (now - timedelta(days=KEEP_DAYS) < end < now - timedelta(minutes=20)):
            continue
        rec = sold.get(key)
        if rec and (rec.get("final") is not None or rec.get("canceled") or rec.get("tries", 0) >= MAX_TRIES):
            continue
        todo.append((end, key, v))
    todo.sort(reverse=True)  # newest first, so fresh results show up quickly
    done = 0
    for _, key, v in todo[:limit] if page else []:
        rec = dict(sold.get(key) or {}, **v)
        try:
            got = fetch_final(page, v["url"])
        except Exception as e:  # keep going
            print(f"sold: {v['url']}: {type(e).__name__}")
            got = {}
        rec.update(got)
        rec["tries"] = rec.get("tries", 0) + 1
        rec["checked"] = now.isoformat(timespec="minutes")
        sold[key] = rec
        done += 1
        time.sleep(2)
    cutoff = now - timedelta(days=KEEP_DAYS)
    sold = {k: r for k, r in sold.items() if r.get("ends_at") and datetime.fromisoformat(r["ends_at"]) > cutoff}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sold, indent=1, sort_keys=True))
    print(f"sold: checked {done} ended auctions, {max(0, len(todo) - limit)} still to check, "
          f"{sum(1 for r in sold.values() if r.get('final') is not None)} with final prices")
    return sold


BID_BUCKETS = (0, 50, 150, 400)  # current-bid bands; low bids jump far more than high ones
POINTS = (24, 8, 3, 1)


def multipliers(sold: dict, min_n: int = 15) -> list[dict]:
    """How final prices compare with the bid N hours before close, per bid band.

    Returns rows {h, lo, hi, n, p25, med, p75} where hi is None for the top band.
    """
    import statistics
    fin = [r for r in sold.values() if r.get("final")]
    rows = []
    for h in POINTS:
        for i, lo in enumerate(BID_BUCKETS):
            hi = BID_BUCKETS[i + 1] if i + 1 < len(BID_BUCKETS) else None
            q = sorted(r["final"] / r[f"bid{h}"] for r in fin
                       if r.get(f"bid{h}") and r[f"bid{h}"] >= lo and (hi is None or r[f"bid{h}"] < hi))
            if len(q) >= min_n:
                rows.append({"h": h, "lo": lo, "hi": hi, "n": len(q), "p25": round(q[len(q) // 4], 2),
                             "med": round(statistics.median(q), 2), "p75": round(q[3 * len(q) // 4], 2)})
    return rows
