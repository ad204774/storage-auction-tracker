from datetime import datetime, timedelta, timezone
from pathlib import Path

from tracker.digest import render
from tracker.geo import distance_from
from tracker.pipeline import Store, filter_nearby, tag_keywords
from tracker.sources import bid13, storagetreasures

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 19, 18, 0, tzinfo=timezone.utc)


def test_bid13_parse():
    rows = bid13.parse((FIX / "bid13.html").read_text())
    assert len(rows) == 2
    a = rows[0]
    assert a.source_id == "336074"
    assert a.url == "https://bid13.com/node/336074"
    assert a.facility == "Secure It Self Storage @ Northpoint"
    assert (a.city, a.state, a.zip_code) == ("Spokane", "WA", "99208")
    assert a.unit_size == "Unit 12109"
    assert "Tools" in a.contents and "Building materials" in a.contents
    assert a.ends_at.isoformat() == "2026-11-20T10:30:00-08:00"
    assert rows[1].city == "Issaquah" and rows[1].contents is None


def test_storagetreasures_parse():
    rows = storagetreasures.parse((FIX / "storagetreasures.html").read_text(), now=NOW)
    assert [r.source_id for r in rows] == ["6943522", "7000001"]
    a, b = rows
    assert a.facility == "Storage Direct Spokane" and a.city == "Spokane"
    assert a.unit_size == "10 x 20" and a.current_bid == 160
    assert a.ends_at == (NOW + timedelta(minutes=39)).replace(second=0)
    assert a.image_url.endswith("thumb.jpg")
    assert b.current_bid == 1010 and b.city == "Kent"
    assert b.ends_at == NOW + timedelta(days=2, hours=3)


def test_distance_and_filter():
    assert distance_from("98024", zip_code="98027", city="Issaquah", state="WA") < 15
    assert distance_from("98024", zip_code=None, city="Kent", state="WA") < 35
    assert distance_from("98024", zip_code=None, city="Spokane", state="WA") > 200
    rows = bid13.parse((FIX / "bid13.html").read_text()) + storagetreasures.parse(
        (FIX / "storagetreasures.html").read_text(), now=NOW)
    nearby, unknown = filter_nearby(rows, "98024", 50)
    assert sorted(a.city for a in nearby) == ["Issaquah", "Kent"]
    assert not unknown


def test_store_tracks_new(tmp_path):
    rows = storagetreasures.parse((FIX / "storagetreasures.html").read_text(), now=NOW)
    s = Store(tmp_path / "seen.json")
    assert s.update(rows[:1], now=NOW) == []  # first run flags nothing as new
    s.save()
    s2 = Store(tmp_path / "seen.json")
    new = s2.update(rows, now=NOW + timedelta(days=1))
    assert [a.source_id for a in new] == ["7000001"]


def test_keywords_and_render():
    rows = storagetreasures.parse((FIX / "storagetreasures.html").read_text(), now=NOW)
    nearby, _ = filter_nearby(rows, "98024", 50)
    for a in nearby:
        a.tags = tag_keywords(a, ["tools", "dresser"])
    assert nearby[0].tags == ["tools"]
    page = render(nearby, nearby, {"home_zip": "98024", "radius_miles": 50}, [], now=NOW)
    assert "Public Storage 25540 - Kent" in page and "NEW" in page
    assert "All open auctions" in page
    email = render(nearby, [], {"home_zip": "98024", "radius_miles": 50}, ["bid13: boom"], now=NOW, for_email=True)
    assert "All open auctions" not in email and "bid13: boom" in email


def test_city_alias():
    assert distance_from("98024", zip_code=None, city="Battleground", state="WA") is not None


def test_site_build(tmp_path):
    import json
    from tracker import site
    rows = storagetreasures.parse((FIX / "storagetreasures.html").read_text(), now=NOW)
    wide, _ = filter_nearby(rows, "98024", 150)
    site.build(tmp_path, wide, wide[:1], {"home_zip": "98024", "home_name": "Fall City, WA",
                                          "radius_miles": 50, "keywords": ["tools"]}, [], now=NOW)
    data = json.loads((tmp_path / "auctions.json").read_text())
    assert [a["city"] for a in data["auctions"]] == ["Kent"]
    assert data["auctions"][0]["new"] and data["home"]["name"] == "Fall City, WA"
    places = json.loads((tmp_path / "places.json").read_text())
    assert any(p["n"] == "Fall City, WA" for p in places)
    assert "Storage Auction Finder" in (tmp_path / "index.html").read_text()


def test_watch_count():
    from tracker.sources.watch import WATCHED, count, count_wa
    assert count_wa("Live Auctions in Washington\nTotal Auctions: 20\nAustin, TX\nKent, WA\nTacoma, WA 98402\n") == 2
    assert count("Showing  1-10 of 1,234 active auctions near washington", WATCHED[1]["pattern"]) == 1234


def test_storagetreasures_photos():
    from tracker.sources import storagetreasures
    base = "https://media.st-prd-1.aws.storagetreasures.com/data/auctions/images/4/6/7/8/9/5/2/"
    html = ('<div class="image-gallery-container">'
            + "".join(f'<img src="{base}{i}/giant.jpg">' for i in (5, 6, 7))
            + f'</div><div class="image-gallery-thumbnail-inner"><img class="image-gallery-thumbnail-image" src="{base}5/giant.jpg"></div>'
            + f'<div class="related"><img src="{base}9/thumb.jpg"></div>')
    assert storagetreasures.parse_photos(html) == [f"{base}{i}/giant.jpg" for i in (5, 6, 7)]
