from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class Auction:
    """One storage unit up for auction, normalized across sources."""

    source: str  # "storagetreasures", "bid13", ...
    source_id: str  # the source's own id for the auction
    url: str
    facility: str
    city: str
    state: str
    zip_code: str | None = None
    address: str | None = None
    unit_size: str | None = None
    contents: str | None = None
    current_bid: float | None = None
    ends_at: datetime | None = None  # timezone-aware
    image_url: str | None = None
    # Filled in by the pipeline
    lat: float | None = None
    lon: float | None = None
    distance_mi: float | None = None
    first_seen: str | None = None
    tags: list[str] = field(default_factory=list)
    photos: list[str] = field(default_factory=list)  # all photo URLs, from the auction's own page

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ends_at"] = self.ends_at.isoformat() if self.ends_at else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Auction":
        d = dict(d)
        if d.get("ends_at"):
            d["ends_at"] = datetime.fromisoformat(d["ends_at"])
        return cls(**d)
