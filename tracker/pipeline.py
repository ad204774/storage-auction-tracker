"""Filter, dedupe and remember auctions between runs."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .geo import haversine_mi, locate, zip_latlon
from .models import Auction


def tag_keywords(a: Auction, keywords: list[str]) -> list[str]:
    text = (a.contents or "").lower()
    return [k for k in keywords if re.search(rf"\b{re.escape(k.lower())}\b", text)]


def filter_nearby(auctions: list[Auction], home_zip: str, radius: float) -> tuple[list[Auction], list[Auction]]:
    """Return (nearby, unknown_location)."""
    home = zip_latlon(home_zip)
    if home is None:
        raise ValueError(f"Unknown home ZIP {home_zip}")
    nearby, unknown = [], []
    for a in auctions:
        pt = locate(zip_code=a.zip_code, city=a.city, state=a.state)
        if pt is None:
            unknown.append(a)
            continue
        a.lat, a.lon = round(pt[0], 4), round(pt[1], 4)
        a.distance_mi = round(haversine_mi(*home, *pt), 1)
        if a.distance_mi <= radius:
            nearby.append(a)
    return nearby, unknown


def dedupe(auctions: list[Auction]) -> list[Auction]:
    out: dict[str, Auction] = {}
    for a in auctions:
        out.setdefault(a.key, a)
    return list(out.values())


class Store:
    """Keeps a small JSON file of every auction seen, so the digest can say what's new."""

    def __init__(self, path: Path):
        self.path = path
        self.seen: dict[str, dict] = {}
        if path.exists():
            self.seen = json.loads(path.read_text())

    def update(self, auctions: list[Auction], now: datetime | None = None) -> list[Auction]:
        """Record auctions; return the ones never seen before."""
        now = now or datetime.now(timezone.utc)
        first_run = not self.seen
        new = []
        for a in auctions:
            prev = self.seen.get(a.key)
            if prev:
                a.first_seen = prev["first_seen"]
                if not a.photos:
                    a.photos = prev.get("photos") or []
            else:
                a.first_seen = now.isoformat(timespec="minutes")
                new.append(a)
            d = a.to_dict()
            # Remember the bid at fixed points before closing (24 h and 8 h), to compare with the final price.
            for k in ("bid24", "bid24_at", "bid8", "bid8_at"):
                if prev and k in prev:
                    d[k] = prev[k]
            if a.ends_at and a.current_bid is not None:
                hours_left = (a.ends_at - now).total_seconds() / 3600
                stamp = now.isoformat(timespec="minutes")
                if hours_left >= 24:
                    d["bid24"], d["bid24_at"] = a.current_bid, stamp
                if hours_left >= 8:
                    d["bid8"], d["bid8_at"] = a.current_bid, stamp
            self.seen[a.key] = d
        if first_run:
            new = []  # everything would be "new" on the first run; don't flag any of it
        # Forget auctions that ended more than 30 days ago.
        cutoff = now.timestamp() - 30 * 86400
        self.seen = {
            k: v for k, v in self.seen.items()
            if not v.get("ends_at") or datetime.fromisoformat(v["ends_at"]).timestamp() > cutoff
        }
        return new

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.seen, indent=1, sort_keys=True))
