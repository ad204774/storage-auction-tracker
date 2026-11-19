"""StorageTreasures.com, the largest online storage auction site.

We load the public state listing page in a headless browser (robots.txt allows
everything except /account/), show 100 auctions per page, and read the auction
tiles from the rendered page. Location is city-level, so distance is measured
from the city's center.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from ..models import Auction

BASE = "https://www.storagetreasures.com"


def _money(s: str | None) -> float | None:
    if not s:
        return None
    m = re.search(r"[\d,]+(?:\.\d+)?", s)
    return float(m.group(0).replace(",", "")) if m else None


def parse(html: str, now: datetime | None = None) -> list[Auction]:
    now = now or datetime.now(timezone.utc)
    soup = BeautifulSoup(html, "html.parser")
    out: list[Auction] = []
    for tile in soup.select("a.auction-tile"):
        href = tile.get("href", "")
        m = re.search(r"/auctions/([a-z]{2})/[^/]+/(\d+)", href)
        if not m:
            continue
        auction_id = m.group(2)

        city_state = tile.select_one(".city-state")
        city, state = "", m.group(1).upper()
        if city_state:
            cs = city_state.get_text(" ", strip=True)
            if "," in cs:
                city, state = [p.strip() for p in cs.rsplit(",", 1)]

        size = tile.select_one(".unit-size")
        contents = tile.select_one(".unit-contains .text")
        bid = tile.select_one(".tile-amount")
        facility = tile.select_one(".facility-name")

        ends_at = None
        cols = tile.select(".countdown-timer-col")
        if len(cols) == 4:
            try:
                d, h, mi, s = (int(c.select_one("h2").get_text(strip=True)) for c in cols)
                ends_at = now + timedelta(days=d, hours=h, minutes=mi, seconds=s)
                ends_at = ends_at.replace(second=0, microsecond=0)
            except (AttributeError, ValueError):
                pass

        image = None
        img = tile.select_one(".auction-img")
        if img and img.get("style"):
            im = re.search(r'url\(["\']?(.*?)["\']?\)', img["style"])
            image = im.group(1) if im else None

        out.append(
            Auction(
                source="storagetreasures",
                source_id=auction_id,
                url=BASE + href if href.startswith("/") else href,
                facility=facility.get_text(" ", strip=True) if facility else "Unknown facility",
                city=city,
                state=state,
                unit_size=size.get_text(" ", strip=True).replace("Approx. Size:", "").strip() if size else None,
                contents=contents.get_text(" ", strip=True) if contents else None,
                current_bid=_money(bid.get_text() if bid else None),
                ends_at=ends_at,
                image_url=image,
            )
        )
    return out


def fetch(page, state: str = "wa", max_pages: int = 30, delay_ms: int = 3_000) -> list[Auction]:
    """`page` is a Playwright page. Walks every result page for the state."""
    page.goto(f"{BASE}/auctions/{state}", wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_selector("a.auction-tile", timeout=60_000)

    # Show 100 per page so the whole state takes ~15 page loads instead of ~100.
    per_page = page.locator("select:has(option[value='100'])").last
    if per_page.count():
        per_page.select_option("100")
        page.wait_for_timeout(delay_ms)

    def go(button_id: str) -> bool:
        """Click prev/next; return False if it's disabled (no more pages)."""
        btn = page.locator(button_id)
        if not btn.count() or "disabled" in (btn.get_attribute("class") or ""):
            return False
        first = page.locator("a.auction-tile").first.get_attribute("href")
        btn.click()
        # Tiles briefly disappear while loading; wait until a different first tile shows.
        page.wait_for_function(
            "h => { const a = document.querySelector('a.auction-tile'); return a && a.getAttribute('href') !== h; }",
            arg=first,
            timeout=60_000,
        )
        page.wait_for_timeout(delay_ms)
        return True

    # The site remembers the last page viewed; make sure we start from page 1.
    for _ in range(max_pages):
        if not go("#pagination-page-prev"):
            break

    seen: dict[str, Auction] = {}
    for _ in range(max_pages):
        for a in parse(page.content()):
            seen.setdefault(a.source_id, a)
        if not go("#pagination-page-next"):
            break
    return list(seen.values())
