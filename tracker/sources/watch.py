"""Sites that currently have no Washington listings. We only count their listings
each day and show a link on the website when any appear, so we know when it's
worth writing a full reader for them."""
from __future__ import annotations

import re

WATCHED = [
    {
        "name": "StorageTreasures Live (in-person) auctions",
        "url": "https://www.storagetreasures.com/live-auctions/wa",
        "pattern": r"Total Auctions:\s*([\d,]+)",
        "wait_ms": 6_000,
    },
    {
        "name": "iBid4Storage",
        "url": "https://www.ibid4storage.com/online-storage-auctions/washington",
        "pattern": r"of\s+([\d,]+)\s+active auctions",
        "wait_ms": 3_000,
    },
]


def count(text: str, pattern: str) -> int | None:
    m = re.search(pattern, text)
    return int(m.group(1).replace(",", "")) if m else None


def check(page) -> list[dict]:
    out = []
    for w in WATCHED:
        n = None
        try:
            page.goto(w["url"], wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(w["wait_ms"])
            n = count(page.inner_text("body"), w["pattern"])
        except Exception as e:  # never let a watched site break the run
            print(f"watch {w['name']}: {type(e).__name__}")
        print(f"watch {w['name']}: {n}")
        out.append({"name": w["name"], "url": w["url"], "count": n})
        page.wait_for_timeout(10_000)  # iBid4Storage asks for 10s between requests
    return out
