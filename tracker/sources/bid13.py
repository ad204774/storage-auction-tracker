"""Bid13 public auction notices.

Bid13 publishes every Washington lien-sale notice on one public page, which its
robots.txt allows (Crawl-delay: 5). Each notice includes the full address, so we
can compute distance from the ZIP code.
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ..models import Auction

BASE = "https://bid13.com"
PACIFIC = ZoneInfo("America/Los_Angeles")


def notices_url(state: str) -> str:
    return f"{BASE}/current-auction-notices/united-states/{state}"


def _field(text: str, name: str) -> str | None:
    m = re.search(rf"{name}\s*:\s*(.+)", text)
    return m.group(1).strip() if m else None


def _parse_time(s: str | None) -> datetime | None:
    if not s:
        return None
    s = re.sub(r"\s+(PST|PDT|PT)$", "", s.strip())
    try:
        return datetime.strptime(s, "%B %d, %Y %I:%M %p").replace(tzinfo=PACIFIC)
    except ValueError:
        return None


def parse(html: str) -> list[Auction]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Auction] = []
    for row in soup.select("li.auction-search-result"):
        text = row.get_text("\n", strip=True)
        # get_text splits "<strong>End</strong>: ..." into two lines; rejoin them.
        text = re.sub(r"\n:\s*", ": ", text)

        link = row.select_one('a[href^="/node/"]')
        if not link:
            continue
        node_id = link["href"].rsplit("/", 1)[-1]

        location = _field(text, "Location") or ""
        # "8908 N Nevada, Spokane, WA, 99208"
        parts = [p.strip() for p in location.split(",")]
        zip_code = parts[-1] if parts and re.fullmatch(r"\d{5}", parts[-1]) else None
        state = parts[-2] if len(parts) >= 3 else "WA"
        city = parts[-3].title() if len(parts) >= 3 else ""

        facility = ""
        for strong in row.select("strong"):
            t = strong.get_text(" ", strip=True)
            if " - " in t and location and location.split(",")[0] in t:
                facility = t.split(" - ")[0].strip()
                break

        desc = _field(text, "Description") or ""
        unit, contents = desc, None
        m = re.match(r"(Unit\s+\S+)\s*-\s*\((.*)\)\s*$", desc)
        if m:
            unit, contents = m.group(1), m.group(2).replace("-", " ").strip() or None

        out.append(
            Auction(
                source="bid13",
                source_id=node_id,
                url=f"{BASE}/node/{node_id}",
                facility=facility or "Unknown facility",
                city=city,
                state=state,
                zip_code=zip_code,
                address=location,
                unit_size=unit,
                contents=contents,
                ends_at=_parse_time(_field(text, "End")),
            )
        )
    return out


def fetch(page, state: str = "washington") -> list[Auction]:
    """`page` is a Playwright page."""
    page.goto(notices_url(state), wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2_000)
    return parse(page.content())
