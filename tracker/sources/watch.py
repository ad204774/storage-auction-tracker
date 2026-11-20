"""Sites that currently have no Washington listings. We only count their listings
each day and show a link on the website when any appear, so we know when it's
worth writing a full reader for them."""
from __future__ import annotations

import re

WATCHED = [
    {
        "name": "StorageTreasures Live (in-person) auctions",
        "url": "https://www.storagetreasures.com/live-auctions/wa",
        # The "Total Auctions" number can include other states, so count WA listings instead.
        "count_wa": True,
        "wait_ms": 8_000,
    },
    {
        "name": "iBid4Storage",
        "url": "https://www.ibid4storage.com/online-storage-auctions/washington",
        "pattern": r"of\s+([\d,]+)\s+active auctions",
        "wait_ms": 3_000,
    },
]


def count_wa(text: str) -> int:
    """Number of listings whose location line ends in ', WA'."""
    return len(re.findall(r",\s*WA\b(?!\w)", text))


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
            text = page.inner_text("body")
            n = count_wa(text) if w.get("count_wa") else count(text, w["pattern"])
        except Exception as e:  # never let a watched site break the run
            print(f"watch {w['name']}: {type(e).__name__}")
        print(f"watch {w['name']}: {n}")
        out.append({"name": w["name"], "url": w["url"], "count": n})
        page.wait_for_timeout(10_000)  # iBid4Storage asks for 10s between requests
    return out
